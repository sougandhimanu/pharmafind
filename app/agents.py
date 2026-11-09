"""The five agents from spec section 4. Each takes and returns pydantic models.

Intake, Alternatives and Safety reviewer are deterministic implementations of the
LLM roles in the spec, so the pipeline runs and evals reproduce fully offline. An
LLM can be layered on top of each, but the code-level checks here stay in place.
"""
from app import guardrails
from app.models import (
    Alternatives, Drug, Location, PharmacyStock, RankedResult, SafetyVerdict, SearchResponse,
)
from app.tools.overpass import find_pharmacies
from app.tools.rxnorm import normalize_drug, related_products
from app.tools.stock import check_stock

STATUS_ORDER = {"in_stock": 0, "low": 1, "unknown": 2, "out_of_stock": 3}


def intake(query: str) -> Drug:
    return normalize_drug(query)


def availability(drug: Drug, location: Location, radius_km: float) -> list[PharmacyStock]:
    """Raises ToolError if pharmacies can't be looked up. Never invents pharmacies."""
    pharmacies = find_pharmacies(location.lat, location.lon, radius_km)
    return [
        PharmacyStock(pharmacy=p, stock=guardrails.enforce_stock_policy(drug, check_stock(p, drug)))
        for p in pharmacies
    ]


def alternatives(drug: Drug) -> Alternatives | None:
    items = related_products(drug)
    if not items:
        return None
    return Alternatives(items=items, disclaimer=guardrails.ALTERNATIVES_DISCLAIMER)


def rank(found: list[PharmacyStock]) -> list[RankedResult]:
    """In stock, then low, then unknown, then out of stock; ties by distance."""
    ordered = sorted(found, key=lambda f: (STATUS_ORDER[f.stock.status], f.pharmacy.distance_km))
    return [RankedResult(rank=i, pharmacy=f.pharmacy, stock=f.stock) for i, f in enumerate(ordered, 1)]


def safety_review(draft: SearchResponse) -> SafetyVerdict:
    """Runs last. Blocks advice-shaped text and unsafe stock or alternatives output."""
    text_parts = [draft.message, *(draft.alternatives.items if draft.alternatives else [])]
    for part in text_parts:
        if pattern := guardrails.contains_advice(part):
            return SafetyVerdict(approved=False, reason=f"advice-like content matched {pattern!r}")
    if draft.alternatives and draft.alternatives.disclaimer != guardrails.ALTERNATIVES_DISCLAIMER:
        return SafetyVerdict(approved=False, reason="alternatives missing pharmacist disclaimer")
    if draft.drug and draft.drug.controlled and any(r.stock.status != "unknown" for r in draft.results):
        return SafetyVerdict(approved=False, reason="controlled substance shown with a stock level")
    if not draft.disclaimer:
        return SafetyVerdict(approved=False, reason="missing disclaimer")
    return SafetyVerdict(approved=True)
