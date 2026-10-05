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
`gcloud projects create lifelive-dashboard-app --name="Lifelive Motorsport dashboard-app"` puis lier la facturation (le script le fait aussi).

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
- `https://dashboard-app.lifelive-motorsport.com/healthz` répond `{"ok":true}`.
- Connexion avec un compte du domaine, puis avec un compte actionnaire ; un compte non listé doit être refusé (« Accès non autorisé »).
- Installer la PWA : Chrome/Android « Ajouter à l'écran d'accueil » ; Safari/iOS « Sur l'écran d'accueil ».
