import os


def _list(name: str) -> list[str]:
    return [x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()]


PROVIDER = os.getenv("DATA_PROVIDER", "demo")  # demo | odoo
ODOO_URL = os.getenv("ODOO_URL", "")  # ex. https://lifelive.odoo.com
ODOO_DB = os.getenv("ODOO_DB", "")
ODOO_API_KEY = os.getenv("ODOO_API_KEY", "")  # clé API de l'utilisateur technique (lecture seule)
CACHE_TTL = int(os.getenv("CACHE_TTL_SECONDS", "300"))

AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
ALLOWED_DOMAIN = os.getenv("ALLOWED_DOMAIN", "lifelive-motorsport.com").lower()
ALLOWED_EMAILS = _list("ALLOWED_EMAILS")  # actionnaires hors domaine

# Nom du site web dans Odoo -> libellé affiché
WEBSHOP_LABELS = {
    "Lifelive Motorsport": "Webshop XC",
    "Goldspeed XC Cross Car tires - European Championship": "Webshop Goldspeed",
}

# Plan (axe) analytique des événements : sous-chaîne de son nom, sans tenir compte des accents ni de la casse.
# Défaut : « MEETING ». Vide = détection automatique (plan dont le nom contient « event » ou « événement »).
EVENT_PLAN = os.getenv("EVENT_PLAN", "meeting")

# Axe analytique « BU » : sert à rattacher chaque événement (axe MEETING) à XC ou à CARS. Nom exact du plan, sans tenir compte de la casse.
BU_PLAN = os.getenv("BU_PLAN", "BU")
VEHICLE_PLAN = os.getenv("VEHICLE_PLAN", "CARS")        # axe analytique dont chaque compte est un véhicule

# Ajustements de marge brute : édition réservée à ces adresses ; stockage « firestore » (production) ou « memory » (démo/essais)
ADMIN_EMAILS = _list("ADMIN_EMAILS")
ADJUSTMENTS_STORE = os.getenv("ADJUSTMENTS_STORE", "memory" if PROVIDER == "demo" else "firestore")

# Chemin des pages du webshop dans le suivi des visites d'Odoo (visites et pages les plus vues ne comptent que ces pages)
WEBSHOP_PATH = os.getenv("WEBSHOP_PATH", "/shop")
VISITS_DAYS = int(os.getenv("VISITS_DAYS", "50"))   # fenêtre fixe des visites (Odoo supprime les visiteurs anonymes inactifs après ~60 jours)
WEBSHOP_STRICT_SITE = os.getenv("WEBSHOP_STRICT_SITE", "false").lower() == "true"   # true : ignorer aussi les produits sans site web précis
PICKING_WEEKS = int(os.getenv("PICKING_WEEKS", "12"))   # nombre de semaines du graphique des commandes préparées
