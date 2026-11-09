"""search(): guard -> normalize -> find pharmacies -> check stock -> rank -> review."""
import logging
from typing import Optional

from app import agents, guardrails
from app.models import Drug, Location, RankedResult, SearchResponse
from app.tools import ToolError
from app.tools.geocode import InvalidZipError, geocode_zip
from app.tools.overpass import pharmacy_source
from app.tools.stock import IS_SIMULATED

log = logging.getLogger("pharmafind")

DEFAULT_RADIUS_KM = 5.0
MAX_QUERY_CHARS = 200


class SearchError(Exception):
    """A request we can't serve. `message` is safe to show the user."""

    def __init__(self, code: str, message: str, http_status: int):
        super().__init__(message)
        self.code, self.message, self.http_status = code, message, http_status


def search(
    query: str,
    zip_code: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> SearchResponse:
    query = (query or "").strip()[:MAX_QUERY_CHARS]
    if category := guardrails.advice_request_category(query):
        log.info("refused advice request category=%s", category)  # never log the query text
        return _response("refused", guardrails.REFUSAL_MESSAGE)
    if not query:
        raise SearchError("missing_drug", "Enter the medicine name from your prescription.", 400)

    location = _resolve_location(zip_code, lat, lon)
    drug = agents.intake(query)
    if not drug.matched:
        return _response("not_found", _not_found_message(drug), drug=drug, location=location)

    try:
        found = agents.availability(drug, location, radius_km)
    except ToolError as exc:
        raise SearchError("pharmacy_lookup_failed", str(exc), 502) from exc

    results = agents.rank(found)
    log.info("search drug=%s controlled=%s pharmacies=%d", drug.name, drug.controlled, len(results))
    if not results:
        msg = f"No pharmacies found within {radius_km:g} km. Try a larger radius or another ZIP code."
        return _response("no_pharmacies", msg, drug=drug, location=location)

    has_stock = any(r.stock.status in ("in_stock", "low") for r in results)
    alternatives = None if has_stock or drug.controlled else agents.alternatives(drug)
    draft = _response("ok", _results_message(drug, results), drug=drug, location=location,
                      results=results, alternatives=alternatives)
    return _reviewed(draft)


def _reviewed(draft: SearchResponse) -> SearchResponse:
    verdict = agents.safety_review(draft)
    if verdict.approved:
        return draft
    log.warning("safety reviewer blocked response: %s", verdict.reason)
    return _response("refused", guardrails.SAFE_FALLBACK_MESSAGE, drug=draft.drug)


def _resolve_location(zip_code: Optional[str], lat: Optional[float], lon: Optional[float]) -> Location:
    if lat is not None and lon is not None:
        try:
            return Location(lat=lat, lon=lon, label="Your current location")
        except ValueError as exc:
            raise SearchError("invalid_location", "That location doesn't look valid.", 422) from exc
    if not zip_code or not zip_code.strip():
        raise SearchError("missing_location", "Enter a ZIP code or use your current location.", 400)
    try:
        return geocode_zip(zip_code)
    except InvalidZipError as exc:
        raise SearchError("invalid_zip", str(exc), 422) from exc
    except ToolError as exc:
        raise SearchError("location_lookup_failed", str(exc), 502) from exc


def _not_found_message(drug: Drug) -> str:
    if drug.suggestions:
        return f"We couldn't match that medicine. Did you mean {' or '.join(drug.suggestions)}?"
    return ("We couldn't match that medicine. Did you mean something else? "
            "Check the spelling on your prescription label.")


def _results_message(drug: Drug, results: list[RankedResult]) -> str:
    n = len(results)
    if drug.controlled:
        return (f"{drug.name} is a controlled medicine. PharmaFind never shows stock for "
                f"controlled medicines online. Call a pharmacy below to confirm availability.")
    in_stock = sum(r.stock.status in ("in_stock", "low") for r in results)
    if in_stock:
        return f"{in_stock} of {n} nearby pharmacies show {drug.name} available (simulated)."
    return (f"None of the {n} nearby pharmacies show {drug.name} in stock right now (simulated). "
            f"Other strengths or forms of the same medicine are listed below. "
            f"{guardrails.ALTERNATIVES_DISCLAIMER}")


def _response(status, message: str, **fields) -> SearchResponse:
    return SearchResponse(
        status=status, message=message, disclaimer=guardrails.DISCLAIMER,
        stock_is_simulated=IS_SIMULATED,
        pharmacy_source=pharmacy_source() if fields.get("results") else None, **fields,
    )
