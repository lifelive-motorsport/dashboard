# Logbook — Lifelive Motorsport

Pour tout ce qui concerne le nom, l'apparence, les couleurs ou les BU, suivre `docs/BRAND.md` (valeurs exactes : `docs/brand-kit/tokens.css` et `docs/brand-kit/bu.ts`, logos officiels : `frontend/brand/`).
L'entreprise s'écrit toujours « Lifelive » ou « Lifelive Motorsport ».

Application : FastAPI (`backend/`) + front en JavaScript sans framework (`frontend/`), hébergée sur Cloud Run ; tests : `cd backend && python -m pytest -q`.
Le cache du service worker (`frontend/sw.js`, constante `C`) se monte à chaque changement du front.

Navigation : 4 chapitres / 8 modules, définis dans `frontend/modules.js` (registre) ; chaque page a une clé « groupe/page » dans `MENU` (`frontend/app.js`) et, côté serveur, ses routes et données dans `backend/app/access.py` (`PAGES`) : ajouter une page ou un module = renseigner ces trois endroits. Les droits des utilisateurs se donnent page par page (Administrer › Équipage).

Langues : l'interface est en français (langue source) avec un bouton FR / EN en haut à droite. Les traductions sont dans `frontend/i18n-en.js` (texte français exact -> anglais ; motifs pour les phrases à valeurs variables) ; un texte absent du dictionnaire reste en français. Tout nouveau texte visible doit être ajouté au dictionnaire. Les formats de nombres suivent `LOCALE()`.
