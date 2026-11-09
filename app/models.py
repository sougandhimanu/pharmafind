"""Typed contracts shared by every tool and agent (spec section 5)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

StockStatus = Literal["in_stock", "low", "out_of_stock", "unknown"]
StockSource = Literal["mock", "call_to_confirm"]
PharmacySource = Literal["openstreetmap", "sample"]
ResponseStatus = Literal["ok", "not_found", "refused", "no_pharmacies"]


class Drug(BaseModel):
    query: str
    name: Optional[str] = None
    rxcui: Optional[str] = None
    matched: bool = False
    controlled: bool = False
    suggestions: list[str] = Field(default_factory=list)
    strength: Optional[str] = None
    form: Optional[str] = None
    quantity: Optional[int] = None
    corrected: bool = False  # True when a misspelling was auto-corrected


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    label: str


class Pharmacy(BaseModel):
    id: str
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    opening_hours: Optional[str] = None
    lat: float
    lon: float
    distance_km: float


class StockResult(BaseModel):
    pharmacy_id: str
    status: StockStatus
    source: StockSource
    note: str = ""


class PharmacyStock(BaseModel):
    pharmacy: Pharmacy
    stock: StockResult


class RankedResult(PharmacyStock):
    rank: int


class Alternatives(BaseModel):
    items: list[str]
    disclaimer: str


class SafetyVerdict(BaseModel):
    approved: bool
    reason: str = ""


class SearchResponse(BaseModel):
    status: ResponseStatus
    drug: Optional[Drug] = None
    location: Optional[Location] = None
    results: list[RankedResult] = Field(default_factory=list)
    alternatives: Optional[Alternatives] = None
    pharmacy_source: Optional[PharmacySource] = None
    stock_is_simulated: bool
    message: str
    disclaimer: str
