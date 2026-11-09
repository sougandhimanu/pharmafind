"""Nearby pharmacies via OpenStreetMap Overpass, with fictional offline samples."""
import math

import httpx

from app.models import Pharmacy, PharmacySource
from app.tools import ToolError, http_client, is_offline, load_json

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OVERPASS_TIMEOUT = httpx.Timeout(25.0, connect=5.0)
MAX_RESULTS = 15


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def pharmacy_source() -> PharmacySource:
    return "sample" if is_offline() else "openstreetmap"


def find_pharmacies(lat: float, lon: float, radius_km: float) -> list[Pharmacy]:
    """Nearest pharmacies within radius, closest first. Raises ToolError, never fabricates."""
    found = _sample_pharmacies(lat, lon) if is_offline() else _overpass(lat, lon, radius_km)
    nearby = [p for p in found if p.distance_km <= radius_km]
    return sorted(nearby, key=lambda p: p.distance_km)[:MAX_RESULTS]


def _sample_pharmacies(lat: float, lon: float) -> list[Pharmacy]:
    return [
        _make(row["id"], row["name"] + " (sample)", row["address"], row["phone"],
              row["opening_hours"], lat + row["dlat"], lon + row["dlon"], lat, lon)
        for row in load_json("sample_pharmacies.json")
    ]


def _overpass(lat: float, lon: float, radius_km: float) -> list[Pharmacy]:
    radius_m = int(radius_km * 1000)
    query = (
        f'[out:json][timeout:20];('
        f'node["amenity"="pharmacy"](around:{radius_m},{lat},{lon});'
        f'way["amenity"="pharmacy"](around:{radius_m},{lat},{lon}););out center tags;'
    )
    elements = _post_with_fallback(query)
    return [p for p in (_from_osm(e, lat, lon) for e in elements) if p]


def _post_with_fallback(query: str) -> list[dict]:
    """Public Overpass instances are often overloaded; try each mirror once."""
    with http_client() as client:
        for url in OVERPASS_URLS:
            try:
                resp = client.post(url, data={"data": query}, timeout=OVERPASS_TIMEOUT)
                resp.raise_for_status()
                return resp.json()["elements"]
            except (httpx.HTTPError, ValueError, KeyError):
                continue
    raise ToolError("Pharmacy lookup is unavailable right now. Try again shortly.")


def _from_osm(el: dict, lat: float, lon: float) -> Pharmacy | None:
    tags = el.get("tags", {})
    plat = el.get("lat") or el.get("center", {}).get("lat")
    plon = el.get("lon") or el.get("center", {}).get("lon")
    if plat is None or plon is None:
        return None
    street = " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")]))
    address = ", ".join(filter(None, [street, tags.get("addr:city")])) or None
    return _make(
        f"osm-{el.get('type', 'node')}-{el['id']}",
        tags.get("name") or tags.get("brand") or "Pharmacy (unnamed on OpenStreetMap)",
        address, tags.get("phone") or tags.get("contact:phone"),
        tags.get("opening_hours"), plat, plon, lat, lon,
    )


def _make(pid, name, address, phone, hours, plat, plon, lat, lon) -> Pharmacy:
    return Pharmacy(
        id=pid, name=name, address=address, phone=phone, opening_hours=hours,
        lat=plat, lon=plon, distance_km=round(haversine_km(lat, lon, plat, plon), 2),
    )
