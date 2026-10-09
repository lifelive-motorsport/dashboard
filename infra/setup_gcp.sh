#!/usr/bin/env bash
# À exécuter dans Google Cloud Shell (console.cloud.google.com) par un administrateur. Idempotent : relançable.
#   GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com ./infra/setup_gcp.sh
# Variables facultatives : PROJECT_ID, REGION, DOMAIN, ALLOWED_EMAILS (actionnaires hors domaine, séparés par des virgules),
#   ADMIN_EMAILS (adresses autorisées à modifier les ajustements de marge brute, séparées par des virgules)
set -euo pipefail
BILLING_ACCOUNT="${BILLING_ACCOUNT:-}"  # facultatif si le projet est déjà lié à la facturation
: "${GOOGLE_CLIENT_ID:?ID client OAuth requis (voir infra/README_DEPLOY.md, étape 3)}"
PROJECT_ID="${PROJECT_ID:-lifelive-dashboard-app}"
REGION="${REGION:-europe-west1}"
DOMAIN="${DOMAIN:-logbook.lifelive-motorsport.com}"
ALLOWED_EMAILS="${ALLOWED_EMAILS:-}"
ADMIN_EMAILS="${ADMIN_EMAILS:-}"
SA="dashboard-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1 || gcloud projects create "$PROJECT_ID" --name="Lifelive Logbook"
if [ -n "$BILLING_ACCOUNT" ]; then
  gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT" >/dev/null
else
  echo "BILLING_ACCOUNT non fourni : la facturation du projet est supposée déjà liée."
fi
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com firestore.googleapis.com

# Projets récents : le compte de service par défaut doit pouvoir construire l'image (sinon « build failed / permission »).
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
for role in roles/cloudbuild.builds.builder roles/run.builder; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="$role" --condition=None >/dev/null 2>&1 || true
done

gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || gcloud iam service-accounts create dashboard-run --display-name="Dashboard (Cloud Run)"

# Firestore : enregistre les ajustements de marge brute (un seul petit document). L'emplacement ne peut plus être changé ensuite.
gcloud firestore databases describe --database='(default)' >/dev/null 2>&1 || \
  gcloud firestore databases create --database='(default)' --location="$REGION" --type=firestore-native
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role=roles/datastore.user --condition=None >/dev/null

# Bucket privé des fiches de paie (PDF déposés depuis l'app) : accès uniforme, jamais public, lisible par le seul compte de service.
STAFF_BUCKET="${STAFF_BUCKET:-${PROJECT_ID}-payslips}"
gcloud storage buckets describe "gs://${STAFF_BUCKET}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${STAFF_BUCKET}" --location="$REGION" --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding "gs://${STAFF_BUCKET}" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin >/dev/null

# Secret : saisi à l'invite (masqué), jamais dans l'historique ni dans le dépôt.
if ! gcloud secrets describe ODOO_API_KEY >/dev/null 2>&1; then
  gcloud secrets create ODOO_API_KEY --replication-policy=automatic
  read -rsp "Clé API Odoo de l'utilisateur en lecture seule : " v; echo
  printf %s "$v" | gcloud secrets versions add ODOO_API_KEY --data-file=-
  unset v
else
  echo "Secret ODOO_API_KEY déjà présent (pour le changer : gcloud secrets versions add ODOO_API_KEY --data-file=-)"
fi
gcloud secrets add-iam-policy-binding ODOO_API_KEY --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor >/dev/null

# Secret de signature des sessions du dashboard (cookie de 14 jours) : généré ici, jamais affiché.
if ! gcloud secrets describe SESSION_SECRET >/dev/null 2>&1; then
  gcloud secrets create SESSION_SECRET --replication-policy=automatic
  head -c 48 /dev/urandom | base64 | tr -d '\n' | gcloud secrets versions add SESSION_SECRET --data-file=-
fi
gcloud secrets add-iam-policy-binding SESSION_SECRET --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor >/dev/null

read -rp "ODOO_URL (ex. https://lifelive-motorsport.odoo.com) : " ODOO_URL
read -rp "ODOO_DB : " ODOO_DB

gcloud run deploy dashboard --source=. --region="$REGION" --service-account="$SA" \
  --allow-unauthenticated --min-instances=0 --max-instances=2 --memory=512Mi --timeout=60 \
  --set-secrets=ODOO_API_KEY=ODOO_API_KEY:latest,SESSION_SECRET=SESSION_SECRET:latest \
  --set-env-vars="^#^DATA_PROVIDER=odoo#ODOO_URL=${ODOO_URL}#ODOO_DB=${ODOO_DB}#AUTH_ENABLED=true#GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}#ALLOWED_DOMAIN=lifelive-motorsport.com#ALLOWED_EMAILS=${ALLOWED_EMAILS}#ADMIN_EMAILS=${ADMIN_EMAILS}#STAFF_BUCKET=${STAFF_BUCKET}"  # séparateur « # » : les e-mails contiennent « @ » et « , »
# --allow-unauthenticated : le service est public, mais /api/* exige un jeton Google valide
# (domaine Workspace ou email de la liste blanche) vérifié côté serveur.

echo "URL Cloud Run : $(gcloud run services describe dashboard --region="$REGION" --format='value(status.url)')"

# Domaine personnalisé (la propriété du domaine doit avoir été vérifiée, voir README_DEPLOY, étape 5).
if gcloud beta run domain-mappings create --service=dashboard --domain="$DOMAIN" --region="$REGION" 2>/tmp/dm.log; then
  gcloud beta run domain-mappings describe --domain="$DOMAIN" --region="$REGION" --format='value(status.resourceRecords)'
  echo "-> Créez chez votre hébergeur DNS l'enregistrement ci-dessus (CNAME vers ghs.googlehosted.com)."
else
  echo "Mappage de domaine non créé (voir /tmp/dm.log) : normal si le domaine n'est pas encore vérifié."
fi
