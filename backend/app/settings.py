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
# Renommage Dashboard -> Logbook : quand CANONICAL_HOST est défini (ex. logbook.lifelive-motorsport.com), les requêtes arrivant sur un ancien nom d'hôte (LEGACY_HOSTS) sont redirigées en 301, chemin et paramètres conservés.
CANONICAL_HOST = os.getenv("CANONICAL_HOST", "").strip().lower()
LEGACY_HOSTS = [h.strip().lower() for h in os.getenv("LEGACY_HOSTS", "dashboard-app.lifelive-motorsport.com").split(",") if h.strip()]
ALLOWED_EMAILS = _list("ALLOWED_EMAILS")  # actionnaires hors domaine

# Nom du site web dans Odoo -> libellé affiché
WEBSHOP_LABELS = {
    "Lifelive Motorsport": "Webshop XC",
    "Goldspeed XC Cross Car tires - European Championship": "Webshop Goldspeed",
}

# Plan (axe) analytique des événements : sous-chaîne de son nom, sans tenir compte des accents ni de la casse.
# Défaut : « MEETING ». Vide = détection automatique (plan dont le nom contient « event » ou « événement »).
EVENT_PLAN = os.getenv("EVENT_PLAN", "meeting|events")

# Axe analytique « BU » : sert à rattacher chaque événement (axe MEETING) à XC ou à CARS. Nom exact du plan, sans tenir compte de la casse.
BU_PLAN = os.getenv("BU_PLAN", "BU")
VEHICLE_PLAN = os.getenv("VEHICLE_PLAN", "CARS")        # axe analytique dont chaque compte est un véhicule

# Ajustements de marge brute : édition réservée à ces adresses ; stockage « firestore » (production) ou « memory » (démo/essais)
ADMIN_EMAILS = _list("ADMIN_EMAILS")
SUPER_USERS = _list("SUPER_USERS")                # Super User : gère les utilisateurs et leurs rôles (Settings › Utilisateurs) ; vide = REFERENCE_EDITORS, puis ADMIN_EMAILS
XC_ONLY_EMAILS = _list("XC_ONLY_EMAILS")          # catégorie « XC » : ces adresses n'accèdent qu'aux pages XC Webshop, Goldspeed, Par événement, Inventory et aux deux contrôles de marges (rien d'autre, ni côté écran ni côté API)
REFERENCE_EDITORS = _list("REFERENCE_EDITORS")        # qui peut ENREGISTRER les hypothèses d'imputation (référence) ; vide = tous les administrateurs. Les autres administrateurs simulent sans enregistrer.
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
MARGIN_FREIGHT_ACCOUNTS = os.getenv("MARGIN_FREIGHT_ACCOUNTS", "602010")                                              # comptes de frais de transport répartis sur le coût réel des articles (vide = aucun)
TN11_OUTLIER_FACTOR = float(os.getenv("TN11_OUTLIER_FACTOR", "3"))      # un coût réel unitaire plus de N fois supérieur au coût Odoo est jugé aberrant (signalé, coût Odoo conservé)
TN11_LABOUR_LIKE = os.getenv("TN11_LABOUR_LIKE", "hourly rate,taux horaire,heure,hour,main d\'oeuvre,main-d\'oeuvre,main d\'œuvre,main-d\'œuvre,labour,labor,montage complet")   # motifs (nom ou catégorie) qui signalent de la main-d'œuvre, en plus des articles de type service
MARGIN_LOOKBACK_MONTHS = int(os.getenv("MARGIN_LOOKBACK_MONTHS", "24"))          # contrôle des marges XC : période des achats pris en compte pour le coût réel estimé
STOCK_LOCATION_LIKE = os.getenv("STOCK_LOCATION_LIKE", "")

# Liens vers Odoo (événements, véhicules) : adresse publique d'Odoo (par défaut ODOO_URL) et modèle de lien vers un compte analytique
ODOO_PUBLIC_URL = os.getenv("ODOO_PUBLIC_URL", "") or ODOO_URL
ODOO_ANALYTIC_LINK = os.getenv("ODOO_ANALYTIC_LINK", "{base}/odoo/account.analytic.account/{id}/action-183")
ODOO_PARTNER_LINK = os.getenv("ODOO_PARTNER_LINK", "{base}/odoo/contacts/{id}/action-1439")            # fournisseurs : factures fournisseurs du contact (action 1439)
ODOO_CLIENT_LINK = os.getenv("ODOO_CLIENT_LINK", "{base}/odoo/contacts/{id}")                          # clients : fiche du contact (l'action 1439 ne montre que des factures fournisseurs, donc rien pour un client)

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
TIMESHEETS_BUCKET = os.getenv("TIMESHEETS_BUCKET", "") or STAFF_BUCKET     # photos et mémos des pointages : bucket dédié (repli sur STAFF_BUCKET)
STAFF_DIRECTOR_PAY = [x.strip() for x in os.getenv("STAFF_DIRECTOR_PAY", "618000").split(",") if x.strip()]         # rémunération des administrateurs / gérants (hors 620/621)
STAFF_DIRECTOR_SOCIAL = [x.strip() for x in os.getenv("STAFF_DIRECTOR_SOCIAL", "618001").split(",") if x.strip()]   # cotisations sociales des administrateurs payées par la société
EXPENSES_EXCLUDED_ACCOUNTS = [x.strip() for x in os.getenv("EXPENSES_EXCLUDED_ACCOUNTS", "611010").split(",") if x.strip()]   # comptes sortis des frais généraux et mentionnés à part (611010 : loyer du bâtiment, mis gratuitement à disposition par les actionnaires)
EXPENSES_VEHICLE_PREFIXES = [x.strip() for x in os.getenv("EXPENSES_VEHICLE_PREFIXES", "615").split(",") if x.strip()]   # comptes des véhicules de service (un compte par véhicule et par nature)
EXPENSES_DEFAULT_PREFIXES = [x.strip() for x in os.getenv("EXPENSES_DEFAULT_PREFIXES", "611,612,614,64").split(",") if x.strip()]   # comptes proposés au départ comme frais généraux
STAFF_FEE_PREFIXES = [x.strip() for x in os.getenv("STAFF_FEE_PREFIXES", "613").split(",") if x.strip()]   # comptes des honoraires des indépendants (hors frais avancés, refacturés)
STAFF_PAY_PREFIXES = [x.strip() for x in os.getenv("STAFF_PAY_PREFIXES", "620,621").split(",") if x.strip()]   # comptes comparés aux fiches de paie : rémunérations et cotisations patronales

# Google Agenda (lecture seule) : réservations des véhicules (ressources) sur les événements de course. Compte de service du dashboard à inviter en lecture
# sur les agendas listés ; sans CALENDAR_SERVICE_ACCOUNT on réutilise GA_SERVICE_ACCOUNT (usurpation de compte de service, aucune clé stockée).
CALENDAR_IDS = [x.strip() for x in re.split(r"[|;,]", os.getenv("CALENDAR_IDS", "")) if x.strip()]    # agendas où sont créés les événements : « Libellé=adresse » (libellé = BU : XC, Modern Rally, Historic Rally, Historic Racing, Logistics), séparés par « | »
CALENDAR_SERVICE_ACCOUNT = os.getenv("CALENDAR_SERVICE_ACCOUNT", "") or GA_SERVICE_ACCOUNT
CALENDAR_EXCLUDE_REGEX = os.getenv("CALENDAR_EXCLUDE_REGEX", r"^\s*\((circuit|rally)\)")       # ressources à ignorer : par défaut les voitures de course (« (Circuit)-… », « (Rally)-… »), qui ne sont pas des véhicules de service
CALENDAR_VEHICLE_REGEX = os.getenv("CALENDAR_VEHICLE_REGEX", "")                                       # ne garder que les ressources dont le nom correspond (vide : toutes les ressources)
GOOGLE_DELEGATED_USER = os.getenv("GOOGLE_DELEGATED_USER", "")                                          # adresse Workspace (ex. planning@…) au nom de laquelle le compte de service agit : délégation à l'échelle du domaine (liste des ressources, puis création d'événements)
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")                                             # clé d'API (Places, Routes, Geocoding) : recherche du lieu, kilomètres, alerte Suisse / Royaume-Uni
LIFELIVE_ORIGIN = os.getenv("LIFELIVE_ORIGIN", "Mercatorstrasse 1, 4780 Sankt Vith, Belgium")           # point de départ des itinéraires
EVENT_TRAVEL_DAYS = int(os.getenv("EVENT_TRAVEL_DAYS", "1"))                                           # jours de trajet ajoutés avant et après l'événement pour l'immobilisation des véhicules (par défaut)
FUEL_SUPPLIER_NAME = os.getenv("FUEL_SUPPLIER_NAME", "DKV Euro Service")                               # fournisseur des cartes carburant (recherche par nom)
FUEL_BUFFER_DAYS = int(os.getenv("FUEL_BUFFER_DAYS", "3"))                                              # jours avant / après un événement pendant lesquels le véhicule est en déplacement
SPEECH_MODEL = os.getenv("SPEECH_MODEL", "chirp_2")                  # modèle Google Speech-to-Text v2 des mémos vocaux
SPEECH_LOCATION = os.getenv("SPEECH_LOCATION", "europe-west4")        # région (UE) : chirp_2 y est disponible
SPEECH_LANGUAGE = os.getenv("SPEECH_LANGUAGE", "fr-FR")
SPEECH_PROJECT = os.getenv("SPEECH_PROJECT", "")                      # vide : projet de l'environnement Cloud Run
TRANSCRIBE = os.getenv("TRANSCRIBE", "on").lower() != "off"          # « off » masque la transcription des mémos
PUBLIC_URL = os.getenv("PUBLIC_URL", "")                            # adresse de l'application, reprise dans les e-mails (ex. https://logbook.lifelive-motorsport.com)
CRON_AUDIENCE = os.getenv("CRON_AUDIENCE", "")                      # audience du jeton OIDC de Cloud Scheduler (adresse du service Cloud Run)
CRON_SERVICE_ACCOUNT = os.getenv("CRON_SERVICE_ACCOUNT", "")        # compte de service autorisé à déclencher les tâches planifiées (alertes de pointage…)
LEAVE_CALENDAR_ID = os.getenv("LEAVE_CALENDAR_ID", "")              # agenda Google des absences (« warnings ») ; vide : recherché par son nom parmi les agendas accessibles
SCHEDULER_LOCATION = os.getenv("SCHEDULER_LOCATION", "europe-west1")      # région des déclencheurs Cloud Scheduler (état affiché au Super User)
