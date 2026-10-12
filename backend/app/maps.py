"""Google Maps (Places, Routes, Geocoding) : recherche du lieu d'un événement, distance depuis Lifelive et alerte si l'itinéraire passe par la Suisse ou le Royaume-Uni.

Nécessite GOOGLE_MAPS_API_KEY (restreinte aux API Places, Routes et Geocoding). En démo, des lieux fictifs sont proposés."""
from __future__ import annotations

import math
import re
import threading

from . import settings

PLACES = "https://places.googleapis.com/v1"
ROUTES = "https://routes.googleapis.com/directions/v2:computeRoutes"
GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
# Zones englobantes (sud, nord, ouest, est) : seuls les points d'itinéraire situés dedans sont vérifiés par géocodage inverse
BOXES = {"CH": (45.7, 47.9, 5.9, 10.6), "GB": (49.8, 60.9, -8.7, 1.9)}
COUNTRY_NAMES = {"CH": "la Suisse", "GB": "le Royaume-Uni"}
_geo_cache: dict[tuple, str] = {}
_lock = threading.Lock()

DEMO_PLACES = [
    {"id": "demo-spa", "name": "Circuit de Spa-Francorchamps", "address": "Route du Circuit 55, 4970 Stavelot, Belgique", "lat": 50.4372, "lng": 5.9714, "country": "BE", "km": 63, "minutes": 55},
    {"id": "demo-silverstone", "name": "Silverstone Circuit", "address": "Silverstone, Towcester NN12 8TN, Royaume-Uni", "lat": 52.0786, "lng": -1.0169, "country": "GB", "km": 780, "minutes": 560},
    {"id": "demo-monza", "name": "Autodromo Nazionale Monza", "address": "Viale di Vedano, 5, 20900 Monza MB, Italie", "lat": 45.6156, "lng": 9.2811, "country": "IT", "km": 930, "minutes": 600, "via": ["CH"]},
    {"id": "demo-ricard", "name": "Circuit Paul Ricard", "address": "2760 Route des Hauts du Camp, 83330 Le Castellet, France", "lat": 43.2506, "lng": 5.7917, "country": "FR", "km": 1170, "minutes": 700},
]


def api_key() -> str:
    """Clé d'API nettoyée (espaces, guillemets et caractères invisibles du copier-coller retirés) ; erreur claire si elle contient encore des caractères non valides."""
    k = re.sub(r"[\u200b-\u200f\u2060\ufeff\s]", "", (settings.GOOGLE_MAPS_API_KEY or "")).strip("\"'“”‘’")
    if not k.isascii():
        raise RuntimeError("la clé GOOGLE_MAPS_API_KEY contient des caractères non valides (copier-coller) : enregistrez-la à nouveau sur le service")
    return k


def configured() -> bool:
    return bool(settings.GOOGLE_MAPS_API_KEY.strip()) or settings.PROVIDER == "demo"


def _get(url: str, **kw):
    import requests
    return requests.get(url, headers={"X-Goog-Api-Key": api_key(), **kw.pop("headers", {})}, timeout=20, **kw)


def _post(url: str, json: dict, headers: dict):
    import requests
    return requests.post(url, json=json, headers={"X-Goog-Api-Key": api_key(), **headers}, timeout=30)


def autocomplete(q: str) -> list[dict]:
    q = q.strip()
    if settings.PROVIDER == "demo":
        return [{"id": p["id"], "text": f'{p["name"]}, {p["address"]}'} for p in DEMO_PLACES if q.lower() in (p["name"] + p["address"]).lower()]
    r = _post(f"{PLACES}:autocomplete", {"input": q, "languageCode": "fr"}, {})
    if r.status_code != 200:
        raise RuntimeError(f"Google Places HTTP {r.status_code} — {_msg(r)}")
    return [{"id": s["placePrediction"]["placeId"], "text": s["placePrediction"]["text"]["text"]} for s in r.json().get("suggestions", []) if "placePrediction" in s][:8]


def _msg(r) -> str:
    try:
        return r.json().get("error", {}).get("message", "")[:300]
    except ValueError:
        return ""


def details(place_id: str) -> dict:
    """{id, name, address, lat, lng, country}"""
    if settings.PROVIDER == "demo":
        p = next((x for x in DEMO_PLACES if x["id"] == place_id), None)
        if not p:
            raise KeyError(place_id)
        return {k: p[k] for k in ("id", "name", "address", "lat", "lng", "country")}
    r = _get(f"{PLACES}/places/{place_id}", params={"languageCode": "fr"}, headers={"X-Goog-FieldMask": "id,displayName,formattedAddress,location,addressComponents"})
    if r.status_code != 200:
        raise RuntimeError(f"Google Places HTTP {r.status_code} — {_msg(r)}")
    j = r.json()
    country = next((c.get("shortText", "") for c in j.get("addressComponents", []) if "country" in c.get("types", [])), "")
    return {"id": j.get("id", place_id), "name": (j.get("displayName") or {}).get("text", ""), "address": j.get("formattedAddress", ""),
            "lat": j["location"]["latitude"], "lng": j["location"]["longitude"], "country": country}


def decode_polyline(s: str) -> list[tuple[float, float]]:
    pts, i, lat, lng = [], 0, 0, 0
    while i < len(s):
        for axis in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += d
            else:
                lng += d
        pts.append((lat / 1e5, lng / 1e5))
    return pts


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    p = math.pi / 180
    x = math.sin((b[0] - a[0]) * p / 2) ** 2 + math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin((b[1] - a[1]) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def _country_at(pt: tuple[float, float]) -> str:
    key = (round(pt[0], 2), round(pt[1], 2))
    with _lock:
        if key in _geo_cache:
            return _geo_cache[key]
    import requests
    r = requests.get(GEOCODE, params={"latlng": f"{pt[0]},{pt[1]}", "result_type": "country", "key": api_key()}, timeout=15)
    code = ""
    if r.status_code == 200:
        res = r.json().get("results", [])
        code = next((c["short_name"] for x in res for c in x.get("address_components", []) if "country" in c.get("types", [])), "")
    with _lock:
        _geo_cache[key] = code
    return code


def countries_crossed(points: list[tuple[float, float]], watch: tuple[str, ...] = ("CH", "GB")) -> set[str]:
    """Pays surveillés traversés par l'itinéraire : points échantillonnés tous les ~8 km, vérifiés par géocodage inverse seulement dans les zones englobantes."""
    sampled, last = [], None
    for p in points:
        if last is None or _km(last, p) >= 8:
            sampled.append(p)
            last = p
    found: set[str] = set()
    for code in watch:
        s, n, w, e = BOXES[code]
        cand = [p for p in sampled if s <= p[0] <= n and w <= p[1] <= e]
        if not cand:
            continue
        step = max(1, len(cand) // 6)                       # au plus ~6 vérifications par zone, réparties sur le tronçon
        for p in cand[::step][:7]:
            if _country_at(p) == code:
                found.add(code)
                break
    return found


def route(place: dict, origin: dict | None = None) -> dict:
    """{km, minutes, via: ['CH', 'GB'], alerts: ['…'], origin_label} : trajet en voiture jusqu'au lieu, depuis `origin` (lieu Google) ou, par défaut, depuis Lifelive."""
    label = (origin.get("name") or origin.get("address") or "le lieu de départ") if origin and origin.get("id") else "Lifelive"
    if settings.PROVIDER == "demo":
        p = next((x for x in DEMO_PLACES if x["id"] == place.get("id")), None) or {"km": 100, "minutes": 90}
        km, minutes = (p["km"], p["minutes"]) if label == "Lifelive" else (250, 200)
        via = (set(p.get("via", [])) if label == "Lifelive" else set()) | ({place.get("country")} & {"CH", "GB"})
        return _result(km, minutes, via, label)
    start = {"placeId": origin["id"]} if origin and origin.get("id") else {"address": settings.LIFELIVE_ORIGIN}
    r = _post(ROUTES, {"origin": start, "destination": {"placeId": place["id"]}, "travelMode": "DRIVE", "languageCode": "fr"},
              {"X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"})
    if r.status_code != 200:
        raise RuntimeError(f"Google Routes HTTP {r.status_code} — {_msg(r)}")
    rt = (r.json().get("routes") or [None])[0]
    if not rt:
        raise RuntimeError("Aucun itinéraire trouvé")
    pts = decode_polyline((rt.get("polyline") or {}).get("encodedPolyline", ""))
    via = countries_crossed(pts) | ({place.get("country")} & {"CH", "GB"})
    return _result(rt.get("distanceMeters", 0) / 1000, int(str(rt.get("duration", "0s")).rstrip("s") or 0) // 60, via, label)


def _result(km: float, minutes: int, via: set[str], label: str = "Lifelive") -> dict:
    return {"km": round(km), "minutes": int(minutes), "via": sorted(via), "origin_label": label, "alerts": [f"L’itinéraire depuis {label} passe par {COUNTRY_NAMES[c]}." for c in sorted(via)]}
