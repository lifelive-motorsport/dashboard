#!/usr/bin/env bash
# Service déjà déployé : crée le bucket privé des fiches de paie et l'active (à coller dans Cloud Shell, une seule fois).
#   ./infra/setup_payslips.sh
set -euo pipefail
PROJECT_ID="${PROJECT_ID:-lifelive-dashboard-app}"
REGION="${REGION:-europe-west1}"
STAFF_BUCKET="${STAFF_BUCKET:-${PROJECT_ID}-payslips}"
SA="dashboard-run@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud config set project "$PROJECT_ID" >/dev/null
gcloud storage buckets describe "gs://${STAFF_BUCKET}" >/dev/null 2>&1 || \
  gcloud storage buckets create "gs://${STAFF_BUCKET}" --location="$REGION" --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding "gs://${STAFF_BUCKET}" --member="serviceAccount:$SA" --role=roles/storage.objectAdmin >/dev/null
gcloud run services update dashboard --region="$REGION" --update-env-vars="STAFF_BUCKET=${STAFF_BUCKET}"
echo "OK : les PDF de fiches de paie se déposent désormais depuis l'app."
