#!/usr/bin/env bash
# À exécuter dans Google Cloud Shell (console.cloud.google.com) par un administrateur. Idempotent : relançable.
#   BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com ./infra/setup_gcp.sh
# Variables facultatives : PROJECT_ID, REGION, DOMAIN, ALLOWED_EMAILS (actionnaires hors domaine, séparés par des virgules)
set -euo pipefail
: "${BILLING_ACCOUNT:?compte de facturation requis (gcloud billing accounts list)}"
: "${GOOGLE_CLIENT_ID:?ID client OAuth requis (voir infra/README_DEPLOY.md, étape 3)}"
PROJECT_ID="${PROJECT_ID:-lifelive-dashboard-app}"
REGION="${REGION:-europe-west1}"
DOMAIN="${DOMAIN:-dashboard-app.lifelive-motorsport.com}"
ALLOWED_EMAILS="${ALLOWED_EMAILS:-}"
SA="dashboard-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1 || gcloud projects create "$PROJECT_ID" --name="Lifelive Dashboard"
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT" >/dev/null
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || gcloud iam service-accounts create dashboard-run --display-name="Dashboard (Cloud Run)"

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

read -rp "ODOO_URL (ex. https://lifelive-motorsport.odoo.com) : " ODOO_URL
read -rp "ODOO_DB : " ODOO_DB

gcloud run deploy dashboard --source=. --region="$REGION" --service-account="$SA" \
  --allow-unauthenticated --min-instances=0 --max-instances=2 --memory=512Mi --timeout=60 \
  --set-secrets=ODOO_API_KEY=ODOO_API_KEY:latest \
  --set-env-vars="^@^DATA_PROVIDER=odoo@ODOO_URL=${ODOO_URL}@ODOO_DB=${ODOO_DB}@AUTH_ENABLED=true@GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}@ALLOWED_DOMAIN=lifelive-motorsport.com@ALLOWED_EMAILS=${ALLOWED_EMAILS}"
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
