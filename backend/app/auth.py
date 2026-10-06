import base64
import hashlib
import hmac
import json
import time

from fastapi import Header, HTTPException, Request, Response

from . import settings

COOKIE = "lm_session"
RENEW_AFTER = 24 * 3600          # session glissante : le cookie est reposé s'il a plus d'un jour


def is_allowed(email: str) -> bool:
    """Adresse autorisée : liste blanche ou domaine Workspace (revérifié à chaque requête, donc un retrait est immédiat)."""
    email = (email or "").lower()
    return email in settings.ALLOWED_EMAILS or email.endswith("@" + settings.ALLOWED_DOMAIN)


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
    if email in settings.ALLOWED_EMAILS or (info.get("hd", "").lower() == settings.ALLOWED_DOMAIN):
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


def require_user(request: Request, response: Response, authorization: str | None = Header(default=None)) -> str:
    """Utilisateur authentifié : cookie de session du dashboard, sinon jeton Google (Authorization: Bearer)."""
    if not settings.AUTH_ENABLED:
        return "anonymous"
    s = read_session(request.cookies.get(COOKIE, ""))
    if s:
        if time.time() - s[1] > RENEW_AFTER:
            set_session_cookie(response, request, s[0])          # session glissante : tant qu'on s'en sert, elle se prolonge
        return s[0]
    return verify_google(authorization)
