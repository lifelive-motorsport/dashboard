from fastapi import Header, HTTPException

from . import settings


def require_user(authorization: str | None = Header(default=None)) -> str:
    """Vérifie le jeton Google (ID token) ; domaine Workspace ou liste blanche."""
    if not settings.AUTH_ENABLED:
        return "anonymous"
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
