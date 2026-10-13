"""Suggestions d'amélioration et signalements de bug : un e-mail, envoyé par le compte Google de Logbook, à chaque Super User.

Ouvert à tous les utilisateurs connectés (même « Non classé ») ; la page d'où part le message et quelques éléments techniques sont joints d'office."""
from __future__ import annotations

import time

from pydantic import BaseModel, Field

from . import mailer, users

KINDS = {"bug": "Bug", "idea": "Suggestion"}
MAX_PER_HOUR = 10
_sent: dict[str, list[float]] = {}


class FeedbackIn(BaseModel):
    kind: str = Field(pattern="^(bug|idea)$")
    message: str = Field(min_length=3, max_length=4000)
    page: str = Field(default="", max_length=120)             # clé « groupe/page »
    title: str = Field(default="", max_length=200)            # intitulé affiché de la page
    url: str = Field(default="", max_length=400)
    lang: str = Field(default="", max_length=5)
    agent: str = Field(default="", max_length=300)
    screen: str = Field(default="", max_length=30)


def send(user: str, body: FeedbackIn) -> int:
    """Envoie le message aux Super Users ; renvoie le nombre de destinataires. Limite : MAX_PER_HOUR messages par heure et par personne."""
    now = time.time()
    recent = [t for t in _sent.get(user.lower(), []) if now - t < 3600]
    if len(recent) >= MAX_PER_HOUR:
        raise PermissionError("Trop de messages envoyés en peu de temps : réessayez plus tard.")
    to = users.supers()
    if not to:
        raise LookupError("Aucun destinataire configuré (SUPER_USERS).")
    where = body.title or body.page or "(page inconnue)"
    subject = f"[Logbook] {KINDS[body.kind]} — {where}"
    text = (f"{KINDS[body.kind]} envoyé par {user}\n\nPage : {where}" + (f" ({body.page})" if body.page and body.title else "") + (f"\nAdresse : {body.url}" if body.url else "")
            + f"\n\n{body.message.strip()}\n\n—\nLangue : {body.lang or '?'} · Écran : {body.screen or '?'}\nNavigateur : {body.agent or '?'}\n")
    for t in to:
        mailer.send(t, subject, text, reply_to=user)
    _sent[user.lower()] = recent + [now]
    return len(to)
