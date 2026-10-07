import os
import re


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

# Session du dashboard : cookie signé (nécessite SESSION_SECRET, dans Secret Manager) valable SESSION_DAYS jours, glissant.
# Sans SESSION_SECRET, seul le jeton Google (≈ 1 h) fait foi et il faut se reconnecter souvent.
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "14"))

# Stock : champ « code PIF » des articles (détecté si vide) et filtre facultatif sur le nom des emplacements internes
STOCK_PIF_FIELD = os.getenv("STOCK_PIF_FIELD", "")
STOCK_LOCATION_LIKE = os.getenv("STOCK_LOCATION_LIKE", "")

# Liens vers Odoo (événements, véhicules) : adresse publique d'Odoo (par défaut ODOO_URL) et modèle de lien vers un compte analytique
ODOO_PUBLIC_URL = os.getenv("ODOO_PUBLIC_URL", "") or ODOO_URL
ODOO_ANALYTIC_LINK = os.getenv("ODOO_ANALYTIC_LINK", "{base}/odoo/account.analytic.account/{id}/action-183")

# Google Analytics 4 (trafic des webshops et du site vitrine). GA_PROPERTY_ID = identifiant NUMÉRIQUE de la propriété (pas « G-… »).
GA_PROPERTY_ID = os.getenv("GA_PROPERTY_ID", "")
GA_PROPERTY_XC = os.getenv("GA_PROPERTY_XC", "")        # facultatif : propriété propre à un site
GA_PROPERTY_GS = os.getenv("GA_PROPERTY_GS", "")
GA_PROPERTY_SITE = os.getenv("GA_PROPERTY_SITE", "")
GA_HOST_XC = os.getenv("GA_HOST_XC", "www.lifelive-motorsport.com")
GA_HOST_GS = os.getenv("GA_HOST_GS", "www.goldspeedtires-xc.com")
GA_HOST_SITE = os.getenv("GA_HOST_SITE", "")             # site vitrine : par défaut le domaine de GA_HOST_XC
GA_SHOP_PATH = os.getenv("GA_SHOP_PATH", "/shop")
GA_SERVICE_ACCOUNT = os.getenv("GA_SERVICE_ACCOUNT", "")  # compte de service à usurper (portée analytics.readonly), ex. dashboard-run@…

# Dépenses marketing : comptes de charges suivis et événement dont l'investissement est signalé en remarque
MARKETING_ACCOUNTS = [x.strip() for x in os.getenv("MARKETING_ACCOUNTS", "602019,602059,612050").split(",") if x.strip()]
MARKETING_INVEST_ACCOUNTS = [x.strip() for x in os.getenv("MARKETING_INVEST_ACCOUNTS", "240050").split(",") if x.strip()]   # comptes INVEST des investissements marketing
MARKETING_INVEST_KEYWORDS = [x.strip().lower() for x in os.getenv("MARKETING_INVEST_KEYWORDS", "graphique,social media,marketing,communication,publicité,photo,vidéo,video").split(",") if x.strip()]   # le compte INVEST contient aussi du matériel : seules les lignes dont le libellé contient un de ces mots sont des investissements marketing
MARKETING_INVEST_TAG = os.getenv("MARKETING_INVEST_TAG", "invest marketing")   # étiquette de contact des fournisseurs dont les lignes INVEST sont des investissements marketing

# Personnel : bucket Cloud Storage PRIVÉ des fiches de paie (PDF). Sans lui, le dépôt de fichiers est désactivé (les chiffres se saisissent à la main).
STAFF_BUCKET = os.getenv("STAFF_BUCKET", "")
STAFF_DIRECTOR_PAY = [x.strip() for x in os.getenv("STAFF_DIRECTOR_PAY", "618000").split(",") if x.strip()]         # rémunération des administrateurs / gérants (hors 620/621)
STAFF_DIRECTOR_SOCIAL = [x.strip() for x in os.getenv("STAFF_DIRECTOR_SOCIAL", "618001").split(",") if x.strip()]   # cotisations sociales des administrateurs payées par la société
EXPENSES_VEHICLE_PREFIXES = [x.strip() for x in os.getenv("EXPENSES_VEHICLE_PREFIXES", "615").split(",") if x.strip()]   # comptes des véhicules de service (un compte par véhicule et par nature)
EXPENSES_DEFAULT_PREFIXES = [x.strip() for x in os.getenv("EXPENSES_DEFAULT_PREFIXES", "611,612,614,64").split(",") if x.strip()]   # comptes proposés au départ comme frais généraux
STAFF_FEE_PREFIXES = [x.strip() for x in os.getenv("STAFF_FEE_PREFIXES", "613").split(",") if x.strip()]   # comptes des honoraires des indépendants (hors frais avancés, refacturés)
STAFF_PAY_PREFIXES = [x.strip() for x in os.getenv("STAFF_PAY_PREFIXES", "620,621").split(",") if x.strip()]   # comptes comparés aux fiches de paie : rémunérations et cotisations patronales

# Google Agenda (lecture seule) : réservations des véhicules (ressources) sur les événements de course. Compte de service du dashboard à inviter en lecture
# sur les agendas listés ; sans CALENDAR_SERVICE_ACCOUNT on réutilise GA_SERVICE_ACCOUNT (usurpation de compte de service, aucune clé stockée).
CALENDAR_IDS = [x.strip() for x in re.split(r"[|;,]", os.getenv("CALENDAR_IDS", "")) if x.strip()]    # agendas où sont créés les événements : « Libellé=adresse » (libellé = BU : XC, Modern Rally, Historic Rally, Historic Racing, Logistics), séparés par « | »
CALENDAR_SERVICE_ACCOUNT = os.getenv("CALENDAR_SERVICE_ACCOUNT", "") or GA_SERVICE_ACCOUNT
CALENDAR_VEHICLE_REGEX = os.getenv("CALENDAR_VEHICLE_REGEX", "")                                       # ne garder que les ressources dont le nom correspond (vide : toutes les ressources)
FUEL_SUPPLIER_NAME = os.getenv("FUEL_SUPPLIER_NAME", "DKV Euro Service")                               # fournisseur des cartes carburant (recherche par nom)
FUEL_BUFFER_DAYS = int(os.getenv("FUEL_BUFFER_DAYS", "3"))                                              # jours avant / après un événement pendant lesquels le véhicule est en déplacement
