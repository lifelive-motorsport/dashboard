# Mise en place Google Cloud + Odoo

## 1. Odoo.sh — utilisateur technique en lecture seule
1. Créer un utilisateur interne `dashboard-api` avec uniquement les droits **Comptabilité : Lecture** (« Auditeur »/lecture seule) et **Ventes : Utilisateur** si lecture des commandes webshop. Aucun droit d'écriture.
2. Dans ses préférences > Sécurité : **Nouvelle clé API** (durée limitée, à renouveler). Ne la transmettre à personne par chat ou e-mail.
3. Tester : `ODOO_URL=… ODOO_DB=… ODOO_API_KEY=… python scripts/odoo_check.py` (le script vérifie aussi que l'écriture est refusée).
   Odoo.sh : la base de production est sur `https://<projet>.odoo.com` ou le domaine personnalisé. Utiliser la **production**, pas une branche de test.

## 2. Google Cloud
1. Admin Workspace/GCP : ouvrir Cloud Shell, cloner le dépôt, lancer `infra/setup_gcp.sh` (crée le projet, active les API, stocke la clé Odoo dans Secret Manager, déploie Cloud Run en `europe-west1`).
2. **Client OAuth** (manuel, console > API et services > Identifiants > ID client OAuth > Application Web) : origine JavaScript autorisée = URL Cloud Run (à ajouter après le 1er déploiement, puis relancer le script avec le `GOOGLE_CLIENT_ID`). Écran de consentement : type « Interne » (réservé au domaine) ; les actionnaires externes passent par `ALLOWED_EMAILS`, ce qui exige le type « Externe » — à trancher.
3. Domaine personnalisé optionnel (ex. `dashboard.lifelive-motorsport.com`) via Cloud Run > Mappages de domaine.
