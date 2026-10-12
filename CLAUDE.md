# Logbook — Lifelive Motorsport

Pour tout ce qui concerne le nom, l'apparence, les couleurs ou les BU, suivre `docs/BRAND.md` (valeurs exactes : `docs/brand-kit/tokens.css` et `docs/brand-kit/bu.ts`, logos officiels : `frontend/brand/`).
L'entreprise s'écrit toujours « Lifelive » ou « Lifelive Motorsport ».

Application : FastAPI (`backend/`) + front en JavaScript sans framework (`frontend/`), hébergée sur Cloud Run ; tests : `cd backend && python -m pytest -q`.
Le cache du service worker (`frontend/sw.js`, constante `C`) se monte à chaque changement du front.

Navigation : 4 chapitres / 8 modules, définis dans `frontend/modules.js` (registre) ; chaque page a une clé « groupe/page » dans `MENU` (`frontend/app.js`) et, côté serveur, ses routes et données dans `backend/app/access.py` (`PAGES`) : ajouter une page ou un module = renseigner ces trois endroits. Les droits des utilisateurs se donnent page par page (Administrer › Équipage).

Langues : l'interface est en français (langue source) avec un bouton FR / EN en haut à droite. Les traductions sont dans `frontend/i18n-en.js` (texte français exact -> anglais ; motifs pour les phrases à valeurs variables) ; un texte absent du dictionnaire reste en français. Tout nouveau texte visible doit être ajouté au dictionnaire. Les formats de nombres suivent `LOCALE()`.

Planifier › Ressources (3 pages : Staff interne, Staff externe, Véhicules ; clés `planifier/res_staff`, `res_ext`, `res_veh`) : réservées au Super User (comme Administrer › Équipage, elle n'est jamais attribuable à une catégorie) ; le compte Google du staff est le champ `google_email` de sa fiche (`backend/app/staff.py`), les prestataires externes sont gardés dans `dashboard/resources` (`backend/app/resources.py`). L'accès à Google Workspace se fait par délégation à l'échelle du domaine (`backend/app/gauth.py`, variable `GOOGLE_DELEGATED_USER`).

Page Planifier › Événements (Super User) : les événements sont créés dans les agendas Google des BU (`backend/app/planning.py`, agendas de `CALENDAR_IDS`) ; Google Agenda reste la seule source de vérité (propriétés partagées `logbook`, `kind`, `lbid`). Lieu, kilomètres et alerte Suisse / Royaume-Uni : `backend/app/maps.py` (variable `GOOGLE_MAPS_API_KEY`, départ `LIFELIVE_ORIGIN`).
