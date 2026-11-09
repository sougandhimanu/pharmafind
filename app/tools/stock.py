"""Inventory seam. MOCK adapter: no public pharmacy stock API exists.

To go real, replace the body of check_stock and keep its signature. Controlled
substance policy is applied by the pipeline (app.guardrails), not here, so it
survives an adapter swap.
"""
import hashlib

from app.models import Drug, Pharmacy, StockResult, StockStatus
from app.tools import load_json

IS_SIMULATED = True

_NOTES: dict[StockStatus, str] = {
    "in_stock": "Simulated: shown as in stock. Call to confirm.",
    "low": "Simulated: shown as low stock. Call to confirm.",
    "out_of_stock": "Simulated: shown as out of stock.",
    "unknown": "Simulated: no stock signal. Call to confirm.",
}


def check_stock(pharmacy: Pharmacy, drug: Drug) -> StockResult:
    inventory = load_json("mock_inventory.json")
    key = (drug.name or drug.query).lower()
    status = inventory["overrides"].get(key) or _hashed_status(pharmacy.id, key, inventory["weights"])
    return StockResult(pharmacy_id=pharmacy.id, status=status, source="mock", note=_NOTES[status])


def _hashed_status(pharmacy_id: str, drug_key: str, weights: dict[str, int]) -> StockStatus:
    digest = hashlib.sha256(f"{pharmacy_id}|{drug_key}".encode()).digest()
    roll = int.from_bytes(digest[:4], "big") % sum(weights.values())
    for status, weight in weights.items():
        if roll < weight:
            return status  # type: ignore[return-value]
        roll -= weight
    raise AssertionError("unreachable: weights exhausted")
