"""Search history in SQLite (temporary store; swap for a managed DB later).

Privacy: the raw query text is never stored (guardrail 5). A row keeps only the
normalized drug the pipeline identified, the outcome, and the location label.
Device coordinates are never stored, only the label "Your current location".
"""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.models import SearchResponse

DEFAULT_DB = Path(__file__).resolve().parent.parent / "pharmafind.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS search_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    outcome         TEXT    NOT NULL,  -- ok | not_found | refused | no_pharmacies | error:<code>
    drug_name       TEXT,
    rxcui           TEXT,
    strength        TEXT,
    form            TEXT,
    quantity        INTEGER,
    controlled      INTEGER NOT NULL DEFAULT 0,
    refusal_category TEXT,
    location_label  TEXT,
    pharmacy_count  INTEGER NOT NULL DEFAULT 0,
    available_count INTEGER NOT NULL DEFAULT 0
)
"""


class HistoryEntry(BaseModel):
    id: int
    created_at: str
    outcome: str
    drug_name: Optional[str] = None
    rxcui: Optional[str] = None
    strength: Optional[str] = None
    form: Optional[str] = None
    quantity: Optional[int] = None
    controlled: bool = False
    refusal_category: Optional[str] = None
    location_label: Optional[str] = None
    pharmacy_count: int = 0
    available_count: int = 0


def _db_path() -> str:
    return os.environ.get("PHARMAFIND_DB", str(DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _insert(**row) -> None:
    row["created_at"] = _now()
    cols = ", ".join(row)
    marks = ", ".join(f":{c}" for c in row)
    with closing(_connect()) as conn, conn:
        conn.execute(f"INSERT INTO search_history ({cols}) VALUES ({marks})", row)


def record_response(resp: SearchResponse, refusal_category: Optional[str] = None) -> None:
    drug = resp.drug if resp.drug and resp.drug.matched else None
    _insert(
        outcome=resp.status,
        drug_name=drug.name if drug else None,
        rxcui=drug.rxcui if drug else None,
        strength=drug.strength if drug else None,
        form=drug.form if drug else None,
        quantity=drug.quantity if drug else None,
        controlled=int(bool(drug and drug.controlled)),
        refusal_category=refusal_category,
        location_label=resp.location.label if resp.location else None,
        pharmacy_count=len(resp.results),
        available_count=sum(r.stock.status in ("in_stock", "low") for r in resp.results),
    )


def record_error(code: str) -> None:
    _insert(outcome=f"error:{code}")


def recent(limit: int = 20) -> list[HistoryEntry]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM search_history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [HistoryEntry(**dict(r)) for r in rows]


def clear() -> int:
    with closing(_connect()) as conn, conn:
        return conn.execute("DELETE FROM search_history").rowcount
