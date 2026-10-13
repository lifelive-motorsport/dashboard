"""Envoi d'e-mails depuis le compte Workspace de Logbook (Gmail API, délégation à l'échelle du domaine, portée gmail.send).

En démonstration, en essais ou si la délégation n'est pas configurée, rien ne part : les messages sont rangés dans OUTBOX (consultables par les essais)."""
from __future__ import annotations

import base64
import logging
from email.message import EmailMessage

from . import gauth, settings

log = logging.getLogger("logbook")
OUTBOX: list[dict] = []


def enabled() -> bool:
    return gauth.configured() and settings.PROVIDER != "demo"


def send(to: str, subject: str, body: str, reply_to: str = "") -> None:
    if not enabled():
        OUTBOX.append({"to": to, "subject": subject, "body": body, "reply_to": reply_to})
        log.info("E-mail non envoyé (envoi désactivé) : %s — %s", to, subject)
        return
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = settings.GOOGLE_DELEGATED_USER
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = gauth.session((gauth.SCOPE_GMAIL_SEND,)).post("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", json={"raw": raw}, timeout=30)
    if r.status_code >= 300:
        try:
            m = r.json()["error"]["message"]
        except Exception:
            m = f"HTTP {r.status_code}"
        raise RuntimeError(f"Envoi de l'e-mail impossible : {m}")
