# Mise en place — Odoo + Google Cloud

Projet : `lifelive-dashboard-app` · région `europe-west1` · domaine `dashboard-app.lifelive-motorsport.com`
(Un ID de projet GCP = minuscules, chiffres, tirets, 6–30 caractères ; le nom affiché peut être différent.)

## 1. Odoo (fait)
Utilisateur technique en lecture seule + clé API. Contrôle : `python scripts/odoo_check.py` doit afficher « Aucun droit d'écriture ».
Après le déploiement, **retirer la clé de l'environnement de la session Claude** (elle ne doit vivre que dans Secret Manager).

## 2. Cloud Shell
Ouvrir https://shell.cloud.google.com avec le compte administrateur Workspace, puis :
```
git clone -b claude/lifelive-motorsport-dashboards-31k234 https://github.com/lifelive-motorsport/dashboard.git
cd dashboard
gcloud billing accounts list        # noter l'ID du compte de facturation
```
Créer d'abord le projet pour pouvoir y configurer OAuth (étape 3) :
`gcloud projects create lifelive-dashboard-app --name="Lifelive Dashboard"` puis lier la facturation (le script le fait aussi).

## 3. Client OAuth Google (manuel, ~5 min)
Console > projet `lifelive-dashboard-app` > API et services :
1. **Écran de consentement OAuth** : type **Externe** ; nom « Lifelive Dashboard » ; e-mails de support = le vôtre. Portées : seulement les basiques (openid, email, profile). Puis **Publier l'application** (état « En production ») : sans cela, seuls les « utilisateurs test » déclarés pourraient se connecter. Avec des portées basiques, aucune vérification Google n'est demandée.
2. **Identifiants > Créer > ID client OAuth > Application Web** ; *Origines JavaScript autorisées* : `https://dashboard-app.lifelive-motorsport.com` (ajouter ensuite l'URL `…run.app` affichée au déploiement si vous voulez tester avant le DNS).
3. Copier l'**ID client** (`….apps.googleusercontent.com`) — ce n'est pas un secret.

## 4. Déploiement
```
BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX \
GOOGLE_CLIENT_ID=….apps.googleusercontent.com \
ALLOWED_EMAILS="actionnaire1@gmail.com,actionnaire2@…" \
./infra/setup_gcp.sh
```
Le script demande : la clé API Odoo (saisie masquée), `ODOO_URL`, `ODOO_DB`. Il peut être relancé pour changer la liste des actionnaires.
Qui accède : tout `@lifelive-motorsport.com` **et** les adresses de `ALLOWED_EMAILS`.

## 5. Domaine
1. Vérifier la propriété de `lifelive-motorsport.com` pour ce compte Google : https://search.google.com/search-console (enregistrement DNS TXT).
2. Le script affiche l'enregistrement à créer (CNAME `dashboard-app` → `ghs.googlehosted.com.`). Le certificat HTTPS est émis automatiquement (quelques minutes à 1 h).

## 6. Contrôles
- `https://dashboard-app.lifelive-motorsport.com/api/health` répond `{"ok":true}`.
- Connexion avec un compte du domaine, puis avec un compte actionnaire ; un compte non listé doit être refusé (« Accès non autorisé »).
- Installer la PWA : Chrome/Android « Ajouter à l'écran d'accueil » ; Safari/iOS « Sur l'écran d'accueil ».


## Ajustements de marge brute (Firestore)

Les ajustements saisis dans « Overview › Ajustements MB » sont enregistrés dans Firestore (un document partagé). Pour un service déjà déployé :

```
gcloud config set project lifelive-dashboard-app
gcloud services enable firestore.googleapis.com
gcloud firestore databases create --database='(default)' --location=europe-west1 --type=firestore-native
gcloud projects add-iam-policy-binding lifelive-dashboard-app \
  --member="serviceAccount:dashboard-run@lifelive-dashboard-app.iam.gserviceaccount.com" --role=roles/datastore.user --condition=None
gcloud run services update dashboard --region=europe-west1 \
  --update-env-vars="^#^ADMIN_EMAILS=adresse1@lifelive-motorsport.com,adresse2@lifelive-motorsport.com"
```

`ADMIN_EMAILS` : seules ces adresses peuvent modifier les ajustements ; les autres utilisateurs les voient en lecture seule.


## Durée de session (rester connecté)

Le jeton Google ne vaut qu'environ 1 heure. Pour rester connecté 14 jours (glissants : la session se prolonge tant qu'on s'en sert), le dashboard échange ce jeton contre un cookie signé. Il lui faut un secret de signature, à créer une fois :

```
gcloud config set project lifelive-dashboard-app
head -c 48 /dev/urandom | base64 | tr -d '\n' | gcloud secrets create SESSION_SECRET --replication-policy=automatic --data-file=-
gcloud secrets add-iam-policy-binding SESSION_SECRET \
  --member="serviceAccount:dashboard-run@lifelive-dashboard-app.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor
gcloud run services update dashboard --region=europe-west1 --update-secrets=SESSION_SECRET=SESSION_SECRET:latest
```

Durée réglable avec la variable `SESSION_DAYS` (14 par défaut). Retirer une adresse de `ALLOWED_EMAILS` coupe son accès immédiatement, même avec un cookie valide. Le lien « Se déconnecter » (pied de page) supprime le cookie.


## Google Analytics (trafic des webshops et du site vitrine)

Le dashboard lit Google Analytics 4 par l'API de données (lecture seule), avec le compte de service du dashboard :

```
gcloud config set project lifelive-dashboard-app
gcloud services enable analyticsdata.googleapis.com iamcredentials.googleapis.com
# le compte de service doit pouvoir générer son propre jeton avec la portée « analytics.readonly »
gcloud iam service-accounts add-iam-policy-binding dashboard-run@lifelive-dashboard-app.iam.gserviceaccount.com \
  --member="serviceAccount:dashboard-run@lifelive-dashboard-app.iam.gserviceaccount.com" --role=roles/iam.serviceAccountTokenCreator
gcloud run services update dashboard --region=europe-west1 \
  --update-env-vars="^#^GA_PROPERTY_ID=123456789#GA_SERVICE_ACCOUNT=dashboard-run@lifelive-dashboard-app.iam.gserviceaccount.com"
```

Dans Google Analytics (Admin › Gestion des accès à la propriété) : ajouter `dashboard-run@lifelive-dashboard-app.iam.gserviceaccount.com` avec le rôle **Lecteur**.

Variables : `GA_PROPERTY_ID` (identifiant NUMÉRIQUE de la propriété, pas « G-… »), ou une propriété par site : `GA_PROPERTY_XC`, `GA_PROPERTY_GS`, `GA_PROPERTY_SITE` ; noms d'hôte : `GA_HOST_XC` (www.lifelive-motorsport.com), `GA_HOST_GS` (www.goldspeedtires-xc.com), `GA_HOST_SITE` (par défaut GA_HOST_XC) ; `GA_SHOP_PATH` (/shop).
