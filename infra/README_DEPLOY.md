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

## Fiches de paie (STAFF costs › Données source)

Les rémunérations sont des données sensibles : tout le personnel (salariés, indépendants, fiches de paie) n'est lisible et modifiable que par les adresses de `ADMIN_EMAILS`. Pour pouvoir déposer les PDF des fiches de paie depuis l'app, il faut un bucket **privé**, créé une seule fois. Dans Cloud Shell, depuis le dépôt cloné :

```
./infra/setup_payslips.sh
```

(`setup_gcp.sh` le fait déjà pour une première installation.) Le script crée le bucket `lifelive-dashboard-app-payslips`, donne l'accès au seul compte de service et active `STAFF_BUCKET` sur Cloud Run, sans redéploiement du code. Ensuite, tous les dépôts mensuels se font dans l'app.

Sans `STAFF_BUCKET`, le dépôt de PDF est désactivé mais tout le reste fonctionne (les chiffres se saisissent à la main). `STAFF_PAY_PREFIXES` (par défaut `620,621`) désigne les comptes comparés aux fiches de paie. `STAFF_FEE_PREFIXES` (`613`) désigne les comptes des honoraires des indépendants : seules les lignes de leurs factures sur ces comptes comptent dans leur coût (les frais avancés refacturés sont exclus). `STAFF_DIRECTOR_PAY` (`618000`) et `STAFF_DIRECTOR_SOCIAL` (`618001`) désignent la rémunération et les cotisations sociales du gérant / administrateur, comparées à part ; les cotisations sont ajoutées à son coût annualisé.

## Frais généraux (GENERAL EXPENSES)

Les comptes de charges retenus se choisissent dans l'application (GENERAL EXPENSES › Données source) ; le choix est enregistré dans Firestore (document `dashboard/expenses`) et seuls les `ADMIN_EMAILS` peuvent le modifier. Tant que rien n'est enregistré, la proposition de départ est celle de `EXPENSES_DEFAULT_PREFIXES` (par défaut `611,612,614,640`). Les achats par BU (60x), le personnel (62x, 618) et le marketing (`MARKETING_ACCOUNTS`) sont traités dans leurs propres rubriques.

## Carburant et agenda des véhicules (SERVICE VEHICLES)

- **Factures de la carte carburant** : lues dans Odoo (lecture seule) chez le fournisseur dont le nom contient `FUEL_SUPPLIER_NAME` (par défaut « DKV Euro Service »), avec leurs pièces jointes. Le texte des PDF est extrait côté serveur (bibliothèque `pypdf`).
- **Agenda Google** : les véhicules sont des ressources invitées aux événements. Étapes : (1) activer l'API Google Calendar du projet (`gcloud services enable calendar-json.googleapis.com`) ; (2) partager en lecture, avec l'adresse du compte de service du dashboard (`dashboard-run@…`), l'agenda où sont créés les événements de course ; (3) renseigner `CALENDAR_IDS` (adresses d'agenda séparées par des virgules) sur Cloud Run. Le compte de service est le même que pour Google Analytics (`GA_SERVICE_ACCOUNT`, usurpation sans clé) ; `CALENDAR_SERVICE_ACCOUNT` permet d'en indiquer un autre.
- Les ressources dont le nom commence par `(Circuit)` ou `(Rally)` (voitures de course) sont ignorées : réglable avec `CALENDAR_EXCLUDE_REGEX`.
- Réglages facultatifs : `CALENDAR_VEHICLE_REGEX` (ne garder que les ressources dont le nom correspond, par exemple `sprinter|citan|camion|remorque`) et `FUEL_BUFFER_DAYS` (jours avant et après un événement pendant lesquels le véhicule est en déplacement, 3 par défaut).

`EXPENSES_EXCLUDED_ACCOUNTS` (par défaut `611010`, loyer du bâtiment mis gratuitement à disposition) : comptes sortis des frais généraux et mentionnés sous le graphique de la page Général.
