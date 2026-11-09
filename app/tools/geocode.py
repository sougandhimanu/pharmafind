"""ZIP code to coordinates via OSM Nominatim, with an offline ZIP table."""
import re
import threading
import time
from functools import lru_cache

import httpx

from app.models import Location
from app.tools import ToolError, http_client, is_offline, load_json

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")

_rate_lock = threading.Lock()
_last_call = 0.0


class InvalidZipError(ValueError):
    pass


def validate_zip(zip_code: str) -> str:
    cleaned = zip_code.strip()
    if not ZIP_RE.match(cleaned):
        raise InvalidZipError("Enter a 5-digit US ZIP code, for example 10001.")
    return cleaned[:5]


def geocode_zip(zip_code: str) -> Location:
    zip5 = validate_zip(zip_code)
    if is_offline():
        return _offline_lookup(zip5)
    return _nominatim_lookup(zip5)


def _offline_lookup(zip5: str) -> Location:
    table = load_json("zip_centroids.json")
    if zip5 not in table:
        known = ", ".join(sorted(table)[:6])
        raise ToolError(f"Offline mode only knows a few demo ZIP codes (e.g. {known}).")
    lat, lon, label = table[zip5]
    return Location(lat=lat, lon=lon, label=f"{zip5} · {label}")


@lru_cache(maxsize=256)
def _nominatim_lookup(zip5: str) -> Location:
    _respect_rate_limit()
    params = {"postalcode": zip5, "country": "us", "format": "json", "limit": 1}
    try:
        with http_client() as client:
            resp = client.get(NOMINATIM_URL, params=params)
            resp.raise_for_status()
            hits = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ToolError("Location lookup is unavailable right now. Try again shortly.") from exc
    if not hits:
        raise ToolError(f"We couldn't find ZIP code {zip5}.")
    hit = hits[0]
    label = hit.get("display_name", zip5).split(",")
    return Location(lat=float(hit["lat"]), lon=float(hit["lon"]),
                    label=f"{zip5} · {', '.join(s.strip() for s in label[1:3])}")


def _respect_rate_limit() -> None:
    """Nominatim policy: at most one request per second."""
    global _last_call
    with _rate_lock:
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
