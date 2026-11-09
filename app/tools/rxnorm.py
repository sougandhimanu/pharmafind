"""Drug normalization via the NLM RxNorm API, with an offline drug list fallback."""
import difflib
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from app.guardrails import is_controlled
from app.models import Drug
from app.tools import http_client, is_offline, load_json

RXNAV = "https://rxnav.nlm.nih.gov/REST"
AUTO_CORRECT_RATIO = 0.84  # above this a misspelling is corrected; below, we ask
SUGGEST_RATIO = 0.6
MAX_PRODUCTS = 8

FORMS = {
    "capsule": "capsule", "capsules": "capsule", "cap": "capsule", "caps": "capsule",
    "tablet": "tablet", "tablets": "tablet", "tab": "tablet", "tabs": "tablet",
    "pill": "tablet", "pills": "tablet", "suspension": "suspension", "solution": "solution",
    "syrup": "syrup", "inhaler": "inhaler", "inhalers": "inhaler", "injection": "injection",
    "pen": "pen", "pens": "pen", "cream": "cream", "ointment": "ointment",
    "patch": "patch", "patches": "patch", "drops": "drops",
}
NOISE_WORDS = {"oral", "er", "xr", "sr", "dr", "ct", "count", "qty", "x", "of", "rx"}
STRENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg/ml|mg|mcg|µg|g|ml|units?|iu|%)(?![a-z])", re.I)
QUANTITY_RE = re.compile(
    r"(?:#\s*(\d+))|(?:(\d+)\s*(" + "|".join(sorted(FORMS, key=len, reverse=True)) + r"|count|ct)\b)",
    re.I,
)


@dataclass
class ParsedRx:
    name_text: str
    strength: Optional[str]
    form: Optional[str]
    quantity: Optional[int]


def parse_prescription(query: str) -> ParsedRx:
    text = query.strip()
    strength = form = None
    quantity = None
    if m := QUANTITY_RE.search(text):
        quantity = int(m.group(1) or m.group(2))
        form = FORMS.get((m.group(3) or "").lower())
        text = text[: m.start()] + " " + text[m.end():]
    if m := STRENGTH_RE.search(text):
        strength = f"{m.group(1)} {m.group(2).lower()}"
        text = text[: m.start()] + " " + text[m.end():]
    elif m := re.search(r"\b(\d+(?:\.\d+)?)\b", text):
        strength = m.group(1)  # unit not given; do not guess one
        text = text[: m.start()] + " " + text[m.end():]
    words = re.findall(r"[a-zA-Z]+", text.lower())
    form = form or next((FORMS[w] for w in words if w in FORMS), None)
    name_words = [w for w in words if w not in FORMS and w not in NOISE_WORDS]
    return ParsedRx(" ".join(name_words), strength, form, quantity)


def normalize_drug(query: str) -> Drug:
    parsed = parse_prescription(query)
    drug = Drug(query=query, strength=parsed.strength, form=parsed.form, quantity=parsed.quantity)
    if not parsed.name_text:
        return drug
    matched = None if is_offline() else _rxnorm_match(parsed.name_text)
    matched = matched or _local_match(parsed.name_text)
    drug = drug.model_copy(update=matched)
    return drug.model_copy(update={"controlled": is_controlled(drug.name, parsed.name_text)})


def related_products(drug: Drug) -> list[str]:
    """Same-ingredient strengths and forms. Listing only, never a recommendation."""
    if not is_offline() and drug.rxcui:
        try:
            return _rxnorm_products(drug.rxcui, drug.name or "")
        except (httpx.HTTPError, ValueError, KeyError):
            pass
    entry = _local_entry(drug.name)
    return entry["products"][:MAX_PRODUCTS] if entry else []


# ---- offline drug list ----------------------------------------------------

def _local_index() -> dict[str, dict]:
    index = {}
    for entry in load_json("drugs.json"):
        index[entry["name"]] = entry
        for brand in entry["brands"]:
            index[brand] = entry
    return index


def _local_entry(name: Optional[str]) -> Optional[dict]:
    return _local_index().get((name or "").lower())


def _local_match(name_text: str) -> dict:
    index = _local_index()
    candidates = [name_text, *name_text.split()]
    for cand in candidates:
        if cand in index:
            entry = index[cand]
            return {"name": entry["name"], "rxcui": entry["rxcui"], "matched": True}
    scored = sorted(
        ((difflib.SequenceMatcher(None, cand, key).ratio(), key) for cand in candidates for key in index),
        reverse=True,
    )
    best_ratio, best_key = scored[0] if scored else (0.0, "")
    if best_ratio >= AUTO_CORRECT_RATIO:
        entry = index[best_key]
        return {"name": entry["name"], "rxcui": entry["rxcui"], "matched": True, "corrected": True}
    suggestions = []
    for ratio, key in scored:
        if ratio < SUGGEST_RATIO or len(suggestions) == 3:
            break
        if index[key]["name"] not in suggestions:
            suggestions.append(index[key]["name"])
    return {"matched": False, "suggestions": suggestions}


# ---- RxNorm API -----------------------------------------------------------

def _rxnorm_match(name_text: str) -> Optional[dict]:
    """Best RxNorm ingredient for the text, or None if RxNorm is unreachable/unsure."""
    try:
        with http_client() as client:
            resp = client.get(f"{RXNAV}/approximateTerm.json",
                              params={"term": name_text, "maxEntries": 5, "option": 1})
            resp.raise_for_status()
            candidates = resp.json().get("approximateGroup", {}).get("candidate", [])
            if not candidates:
                return None
            rxcui = candidates[0]["rxcui"]
            props = client.get(f"{RXNAV}/rxcui/{rxcui}/properties.json").json()["properties"]
            term = props["name"].lower()
            ratio = difflib.SequenceMatcher(None, name_text, term).ratio()
            if ratio < AUTO_CORRECT_RATIO:
                return None  # too far from what was typed; let the local list decide or ask
            name = term
            if props.get("tty") not in ("IN", "PIN", "MIN"):
                name, rxcui = _ingredient_of(client, rxcui) or (term, rxcui)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None
    return {"name": name, "rxcui": rxcui, "matched": True, "corrected": ratio < 1.0}


def _ingredient_of(client: httpx.Client, rxcui: str) -> Optional[tuple[str, str]]:
    data = client.get(f"{RXNAV}/rxcui/{rxcui}/related.json", params={"tty": "IN"}).json()
    groups = data.get("relatedGroup", {}).get("conceptGroup", []) or []
    concepts = [c for g in groups for c in g.get("conceptProperties", []) or []]
    if not concepts:
        return None
    if len(concepts) == 1:
        return concepts[0]["name"].lower(), concepts[0]["rxcui"]
    return " / ".join(sorted(c["name"].lower() for c in concepts)), rxcui


def _rxnorm_products(rxcui: str, ingredient: str) -> list[str]:
    with http_client() as client:
        resp = client.get(f"{RXNAV}/rxcui/{rxcui}/related.json", params={"tty": "SCD"})
        resp.raise_for_status()
        groups = resp.json().get("relatedGroup", {}).get("conceptGroup", []) or []
    # Single-ingredient products only: combinations are a different drug, not a strength/form.
    same = re.compile(rf"^{re.escape(ingredient)} \d(?!.* / )", re.I)
    names = sorted({c["name"] for g in groups for c in g.get("conceptProperties", []) or []
                    if same.match(c["name"])}, key=_strength_value)
    if not names:
        raise ValueError("no related products")
    return names[:MAX_PRODUCTS]


def _strength_value(product: str) -> float:
    m = re.search(r"\d+(?:\.\d+)?", product)
    return float(m.group()) if m else 0.0
