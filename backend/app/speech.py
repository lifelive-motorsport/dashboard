"""Transcription des mémos vocaux (Consigner › Pointages) par Google Cloud Speech-to-Text v2.

Le navigateur envoie le mémo en WAV 16 kHz mono 16 bits (conversion faite sur le téléphone : Chrome et Safari n'enregistrent pas le même format) ; le serveur le découpe en
morceaux de moins d'une minute (limite de la reconnaissance synchrone), les envoie à Google (région UE, modèle SPEECH_MODEL) et renvoie le texte. Rien n'est conservé par Google."""
from __future__ import annotations

import base64
import io
import wave

from . import settings

CHUNK_SECONDS = 50
MAX_SECONDS = 180


class SpeechError(Exception):
    pass


def _session():
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(creds), settings.SPEECH_PROJECT or project


def _recognize(chunk: bytes) -> str:
    """Un morceau de WAV (< 1 min) -> texte. Isolé pour pouvoir être remplacé dans les essais."""
    s, project = _session()
    loc = settings.SPEECH_LOCATION
    host = "speech.googleapis.com" if loc == "global" else f"{loc}-speech.googleapis.com"
    body = {"config": {"explicitDecodingConfig": {"encoding": "LINEAR16", "sampleRateHertz": 16000, "audioChannelCount": 1}, "languageCodes": [settings.SPEECH_LANGUAGE],
                       "model": settings.SPEECH_MODEL}, "content": base64.b64encode(chunk).decode()}
    r = s.post(f"https://{host}/v2/projects/{project}/locations/{loc}/recognizers/_:recognize", json=body, timeout=60)
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = f"HTTP {r.status_code}"
        raise SpeechError(msg)
    return " ".join((x.get("alternatives") or [{}])[0].get("transcript", "").strip() for x in r.json().get("results", [])).strip()


def transcribe_wav(data: bytes) -> str:
    try:
        w = wave.open(io.BytesIO(data))
    except Exception:
        raise SpeechError("Fichier audio illisible (WAV 16 kHz mono attendu)")
    with w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
            raise SpeechError("Format audio inattendu (WAV 16 kHz mono 16 bits attendu)")
        if w.getnframes() > MAX_SECONDS * 16000:
            raise SpeechError(f"Mémo trop long ({MAX_SECONDS // 60} minutes au maximum)")
        parts = []
        while True:
            frames = w.readframes(CHUNK_SECONDS * 16000)
            if not frames:
                break
            buf = io.BytesIO()
            with wave.open(buf, "wb") as o:
                o.setnchannels(1)
                o.setsampwidth(2)
                o.setframerate(16000)
                o.writeframes(frames)
            parts.append(buf.getvalue())
    return " ".join(t for t in (_recognize(p) for p in parts) if t).strip()
