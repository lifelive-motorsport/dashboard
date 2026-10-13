import base64
import hashlib
import hmac
import json
import time

from fastapi import Header, HTTPException, Request, Response

from . import access, settings, users

COOKIE = "lm_session"
RENEW_AFTER = 24 * 3600          # session glissante : le cookie est reposé s'il a plus d'un jour


def is_allowed(email: str) -> bool:
    """Adresse autorisée : liste blanche ou domaine Workspace (revérifié à chaque requête, donc un retrait est immédiat)."""
    email = (email or "").lower()
    return email in settings.ALLOWED_EMAILS or email.endswith("@" + settings.ALLOWED_DOMAIN) or users.is_registered(email)


def verify_google(authorization: str | None) -> str:
    """Vérifie le jeton Google (ID token, valable ~1 h) ; domaine Workspace ou liste blanche. Renvoie l'adresse."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentification requise")
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token
    try:
        info = id_token.verify_oauth2_token(authorization[7:], g_requests.Request(), settings.GOOGLE_CLIENT_ID)
    except ValueError:
        raise HTTPException(401, "Jeton invalide")
    email = (info.get("email") or "").lower()
    if not info.get("email_verified"):
        raise HTTPException(403, "Email non vérifié")
    if email in settings.ALLOWED_EMAILS or (info.get("hd", "").lower() == settings.ALLOWED_DOMAIN) or users.is_registered(email):
        return email
    raise HTTPException(403, "Accès non autorisé")


# ---- Session propre au dashboard : cookie signé (HMAC), HttpOnly, durée SESSION_DAYS -----------------------------------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _mac(body: str) -> str:
    return _b64(hmac.new(settings.SESSION_SECRET.encode(), body.encode(), hashlib.sha256).digest())


def make_session(email: str, now: float | None = None) -> str:
    now = int(now or time.time())
    body = _b64(json.dumps({"e": email, "iat": now, "exp": now + settings.SESSION_DAYS * 86400}, separators=(",", ":")).encode())
    return f"{body}.{_mac(body)}"


def read_session(value: str, now: float | None = None) -> tuple[str, int] | None:
    """(adresse, date d'émission) si le cookie est authentique, non expiré et que l'adresse est toujours autorisée."""
    if not settings.SESSION_SECRET or not value or "." not in value:
        return None
    body, mac = value.rsplit(".", 1)
    if not hmac.compare_digest(mac, _mac(body)):
        return None
    try:
        p = json.loads(_unb64(body))
    except ValueError:
        return None
    if p.get("exp", 0) < (now or time.time()) or not is_allowed(p.get("e", "")):
        return None
    return p["e"], int(p.get("iat", 0))


def set_session_cookie(response: Response, request: Request, email: str) -> None:
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE, make_session(email), max_age=settings.SESSION_DAYS * 86400, httponly=True, secure=secure,
                        samesite="strict", path="/")


def role(email: str) -> str:
    return "custom" if users.restricted(email) else "full"


def _identify(request: Request, response: Response, authorization: str | None) -> str:
    if not settings.AUTH_ENABLED:
        return "anonymous"
    s = read_session(request.cookies.get(COOKIE, ""))
    if s:
        if time.time() - s[1] > RENEW_AFTER:
            set_session_cookie(response, request, s[0])          # session glissante : tant qu'on s'en sert, elle se prolonge
        return s[0]
    return verify_google(authorization)


# ---- « Voir comme » : le Super User ouvre Logbook avec les droits d'un autre utilisateur (essais, assistance) -------------------------------------
VIEWAS = "lm_viewas"
VIEWAS_HOURS = 2


def make_viewas(real: str, target: str, write: bool, now: float | None = None) -> str:
    now = int(now or time.time())
    body = _b64(json.dumps({"r": real, "a": target, "w": bool(write), "exp": now + VIEWAS_HOURS * 3600}, separators=(",", ":")).encode())
    return f"{body}.{_mac(body)}"


def read_viewas(value: str, real: str, now: float | None = None) -> dict | None:
    """{r, a, w} si le cookie est authentique, non expiré, lié à cette session et que son auteur est (toujours) Super User."""
    if not value or "." not in value or not settings.SESSION_SECRET:
        return None
    body, mac = value.rsplit(".", 1)
    if not hmac.compare_digest(mac, _mac(body)):
        return None
    try:
        p = json.loads(_unb64(body))
    except ValueError:
        return None
    if p.get("exp", 0) < (now or time.time()) or p.get("r") != real or not users.is_super(real) or not is_allowed(p.get("a", "")):
        return None
    return p


def set_viewas_cookie(response: Response, request: Request, real: str, target: str, write: bool) -> None:
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(VIEWAS, make_viewas(real, target, write), max_age=VIEWAS_HOURS * 3600, httponly=True, secure=secure, samesite="strict", path="/")


def real_user(request: Request, response: Response, authorization: str | None = Header(default=None)) -> str:
    """Utilisateur réellement connecté, sans « voir comme » (pour gérer le mode lui-même)."""
    return _identify(request, response, authorization)


_audit = None


def audit_viewas(real: str, target: str, method: str, path: str) -> None:
    """Journal des actions faites en « voir comme » (écritures seulement)."""
    global _audit
    import logging
    import uuid
    from datetime import datetime, timezone
    logging.getLogger("logbook").warning("VOIR COMME : %s agit en tant que %s — %s %s", real, target, method, path)
    try:
        from .timesheets import Coll
        _audit = _audit or Coll("audit_viewas")
        i = uuid.uuid4().hex[:12]
        _audit.put(i, {"id": i, "at": datetime.now(timezone.utc).isoformat(), "real": real, "as": target, "method": method, "path": path})
    except Exception:
        logging.getLogger("logbook").exception("Journal « voir comme » indisponible")


def require_user(request: Request, response: Response, authorization: str | None = Header(default=None)) -> str:
    """Utilisateur authentifié : cookie de session du dashboard, sinon jeton Google (Authorization: Bearer).
    Une catégorie d'utilisateurs (pages cochées par le Super User) n'ouvre que les routes de ses pages (voir access.py).
    Si un Super User a activé « Voir comme », c'est l'utilisateur choisi qui est renvoyé (lecture seule, sauf modifications autorisées et journalisées)."""
    user = _identify(request, response, authorization)
    va = read_viewas(request.cookies.get(VIEWAS, ""), user) if users.is_super(user) else None
    if va:
        request.state.viewing_as = {"real": user, "as": va["a"], "write": bool(va["w"])}
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if not va["w"]:
                raise HTTPException(403, "Mode « Voir comme » en lecture seule : quittez-le ou autorisez les modifications pour agir en tant que cet utilisateur.")
            audit_viewas(user, va["a"], request.method, request.url.path)
        user = va["a"]
    pages = users.pages_of(user)
    if pages is not None and not access.path_ok(request.url.path, pages):
        raise HTTPException(403, "Cette page n'est pas incluse dans votre catégorie d'utilisateur")
    return user
