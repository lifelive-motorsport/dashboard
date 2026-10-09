# Logbook — Lifelive Motorsport

Pour tout ce qui concerne le nom, l'apparence, les couleurs ou les BU, suivre `docs/BRAND.md` (valeurs exactes : `docs/brand-kit/tokens.css` et `docs/brand-kit/bu.ts`, logos officiels : `frontend/brand/`).
L'entreprise s'écrit toujours « Lifelive » ou « Lifelive Motorsport ».

Application : FastAPI (`backend/`) + front en JavaScript sans framework (`frontend/`), hébergée sur Cloud Run ; tests : `cd backend && python -m pytest -q`.
Le cache du service worker (`frontend/sw.js`, constante `C`) se monte à chaque changement du front.
