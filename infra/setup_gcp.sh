#!/usr/bin/env bash
# À exécuter UNE FOIS dans Google Cloud Shell (console.cloud.google.com) par un admin du projet.
# Usage : PROJECT_ID=lifelive-dashboard BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX ./infra/setup_gcp.sh
set -euo pipefail
: "${PROJECT_ID:?}" "${BILLING_ACCOUNT:?}"
REGION="${REGION:-europe-west1}"
SA="dashboard-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects create "$PROJECT_ID" --name="Lifelive Dashboard" 2>/dev/null || echo "Projet déjà existant"
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudscheduler.googleapis.com

gcloud iam service-accounts create dashboard-run --display-name="Dashboard (Cloud Run)" 2>/dev/null || true

# Secrets : saisis à l'invite, jamais dans l'historique ni dans le dépôt.
for s in ODOO_API_KEY; do
  gcloud secrets describe "$s" >/dev/null 2>&1 || gcloud secrets create "$s" --replication-policy=automatic
  read -rsp "Valeur de $s (clé API Odoo, lecture seule) : " v; echo
  printf %s "$v" | gcloud secrets versions add "$s" --data-file=-
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:$SA" --role=roles/secretmanager.secretAccessor >/dev/null
done

read -rp "ODOO_URL (ex. https://lifelive.odoo.com) : " ODOO_URL
read -rp "ODOO_DB : " ODOO_DB
read -rp "GOOGLE_CLIENT_ID (client OAuth Web, voir README_DEPLOY) : " GOOGLE_CLIENT_ID
read -rp "ALLOWED_EMAILS (actionnaires hors domaine, séparés par des virgules, peut être vide) : " ALLOWED_EMAILS

gcloud run deploy dashboard --source=. --region="$REGION" --service-account="$SA" \
  --allow-unauthenticated --min-instances=0 --max-instances=2 --memory=512Mi \
  --set-secrets=ODOO_API_KEY=ODOO_API_KEY:latest \
  --set-env-vars="^@^DATA_PROVIDER=odoo@ODOO_URL=${ODOO_URL}@ODOO_DB=${ODOO_DB}@AUTH_ENABLED=true@GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}@ALLOWED_DOMAIN=lifelive-motorsport.com@ALLOWED_EMAILS=${ALLOWED_EMAILS}"
# --allow-unauthenticated : l'accès est contrôlé par l'application (jeton Google vérifié côté serveur).
gcloud run services describe dashboard --region="$REGION" --format='value(status.url)'
