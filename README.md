# Lifelive Motorsport — Dashboard

Application web (PWA) de pilotage : CA, marge brute, trésorerie, créances, dettes, hit-parade clients et webshops, par BU (XC / CARS).

## Règles métier (validées avec le MD)
- **BU = 3 derniers chiffres** des comptes à 6 chiffres `602` (frais), `603` (sous-traitance), `604` (achats), `700` (CA) — voir `backend/app/bu.py`.
- **CA** = −solde des 700. **Marge brute** = CA − (602 + 603 + 604). Personnel (62) et véhicules (615) **exclus** : non imputables à une BU.
- Les comptes dont le nom commence par `old -` sont ignorés (attention : « **Gold**speed » n'est pas un compte old).
- Regroupements : **XC** = Manufacturer, Workshop, Race team, Goldspeed EAX, Events, Webshop, Others, Sales & Marketing ; **CARS** = Modern Rally, Historic Rally, Historic Racing, CARS Others. `700000/700099/604099` = « Non affecté ».

## Lancer en local (données fictives)
```
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
pytest   # CHART_XLSX=<export plan comptable> pour contrôler la couverture des comptes
```

## Configuration (variables d'environnement)
`DATA_PROVIDER=odoo`, `ODOO_URL`, `ODOO_DB`, `ODOO_API_KEY` (utilisateur technique en lecture seule, via Secret Manager) ;
`AUTH_ENABLED=true`, `GOOGLE_CLIENT_ID`, `ALLOWED_DOMAIN`, `ALLOWED_EMAILS` (actionnaires hors domaine) ; `CACHE_TTL_SECONDS` (300).

## État
- Fait : mapping BU testé contre le plan comptable, API, PWA responsive, mode démo, authentification Google (non testée sans client ID), Dockerfile (Cloud Run).
- Connecteur Odoo : P&L, créances, dettes, trésorerie écrits mais **non testés** sur une vraie base.
- À faire : hit-parade clients et webshops côté Odoo, déploiement Cloud Run, comparaison des chiffres avec l'analyse de septembre 2026.
