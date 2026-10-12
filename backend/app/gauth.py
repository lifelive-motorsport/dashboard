"""Authentification Google par délégation à l'échelle du domaine, sans clé stockée.

Le compte de service du dashboard (CALENDAR_SERVICE_ACCOUNT / GA_SERVICE_ACCOUNT) signe lui-même, via l'API IAM Credentials (rôle « Créateur de jetons de
compte de service » sur lui-même), une demande de jeton au nom de GOOGLE_DELEGATED_USER. Un super-administrateur Workspace doit avoir autorisé l'ID client
du compte de service et les portées utilisées (Console d'administration › Sécurité › Contrôle des accès et des données › Contrôles des API › Délégation à l'échelle du domaine)."""
from __future__ import annotations

import threading

from . import settings

_lock = threading.Lock()
_sessions: dict[tuple, object] = {}

SCOPE_DIRECTORY = "https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly"
SCOPE_USERS = "https://www.googleapis.com/auth/admin.directory.user.readonly"
SCOPE_CALENDAR = "https://www.googleapis.com/auth/calendar"


def configured() -> bool:
    return bool(settings.GOOGLE_DELEGATED_USER and settings.CALENDAR_SERVICE_ACCOUNT)


def session(scopes: tuple[str, ...]):
    """Session HTTP autorisée au nom de GOOGLE_DELEGATED_USER pour ces portées."""
    key = tuple(scopes)
    with _lock:
        if key not in _sessions:
            import google.auth
            from google.auth import iam
            from google.auth.transport.requests import AuthorizedSession, Request
            from google.oauth2 import service_account
            source, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            signer = iam.Signer(Request(), source, settings.CALENDAR_SERVICE_ACCOUNT)
            creds = service_account.Credentials(signer, settings.CALENDAR_SERVICE_ACCOUNT, "https://oauth2.googleapis.com/token", scopes=list(scopes), subject=settings.GOOGLE_DELEGATED_USER)
            _sessions[key] = AuthorizedSession(creds)
        return _sessions[key]
