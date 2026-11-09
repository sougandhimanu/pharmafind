"""Medical-safety guardrails enforced in code (spec section 6).

These checks are deliberately simple and deterministic so they cannot be
"prompted away". Any LLM layer added later sits on top of them, not instead.
"""
import re
from typing import Optional

from app.models import Drug, StockResult

DISCLAIMER = (
    "PharmaFind does not give medical advice. Stock levels shown here are simulated "
    "for demonstration; call the pharmacy to confirm before you go. For questions "
    "about your medicine, ask your pharmacist or prescriber."
)
ALTERNATIVES_DISCLAIMER = "Ask your pharmacist or prescriber before switching."
CONTROLLED_NOTE = (
    "Controlled medicine: availability is never shown online. Call the pharmacy to confirm."
)
REFUSAL_MESSAGE = (
    "PharmaFind only helps you find where to fill a prescription. It can't answer "
    "questions about how to take a medicine, combining medicines, whether a medicine "
    "is right for you, or changing medicines. Please ask your pharmacist or prescriber."
)
SAFE_FALLBACK_MESSAGE = (
    "We couldn't show this answer safely. Please ask your pharmacist or prescriber."
)

# Generic and brand names of US controlled substances (DEA schedules II-V) that
# users are likely to type. Matching is on whole words, case-insensitive.
CONTROLLED_SUBSTANCES = frozenset({
    "oxycodone", "oxycontin", "percocet", "roxicodone", "hydrocodone", "vicodin", "norco",
    "morphine", "fentanyl", "duragesic", "codeine", "tramadol", "ultram", "methadone",
    "hydromorphone", "dilaudid", "tapentadol", "buprenorphine", "suboxone",
    "amphetamine", "dextroamphetamine", "adderall", "lisdexamfetamine", "vyvanse",
    "methylphenidate", "ritalin", "concerta", "dexmethylphenidate", "focalin",
    "alprazolam", "xanax", "lorazepam", "ativan", "diazepam", "valium",
    "clonazepam", "klonopin", "temazepam", "zolpidem", "ambien", "eszopiclone",
    "pregabalin", "lyrica", "carisoprodol", "soma", "modafinil", "provigil",
    "phenobarbital", "testosterone", "ketamine",
})

# Requests for advice we must refuse, grouped by category.
ADVICE_REQUEST_PATTERNS: dict[str, tuple[str, ...]] = {
    "dosing": (
        r"\bhow (much|many)\b", r"\bhow often\b", r"\b(dose|doses|dosage|dosing|overdose)\b",
        r"\b(can|should) i take\b", r"\btimes (a|per) day\b", r"\bmissed\b",
    ),
    "interaction": (
        r"\binteract", r"\b(mix|mixing|combine|combining)\b", r"\bwith (alcohol|my other)\b",
        r"\btogether\b",
    ),
    "safety": (
        r"\bsafe\b", r"\bside effects?\b", r"\bpregnan", r"\bbreastfeed", r"\ballerg",
    ),
    "substitution": (
        r"\b(swap|switch|substitute|substitution|replace|instead)\b", r"\bcheaper\b",
    ),
    "diagnosis": (
        r"\bdiagnos", r"\bsymptoms?\b", r"\bdo i have\b", r"\bwhat should i take\b",
    ),
}

# Advice-shaped content that must never appear in an outgoing response.
ADVICE_CONTENT_PATTERNS: tuple[str, ...] = (
    r"\b(take|use|give)\s+\d", r"\bevery\s+\d+\s*(hours?|hrs?)\b",
    r"\b\d+\s*(times|x)\s*(a|per)\s*day\b", r"\binstead\b", r"\bswitch to\b",
    r"\byou (should|could|can|may) (take|switch|use|try|stop|combine)\b",
    r"\b(is|are|it's) (safe|unsafe)\b", r"\binteract", r"\bdiagnos",
    r"\bmax(imum)? (daily )?dose\b",
)


def advice_request_category(text: str) -> Optional[str]:
    """Return the advice category a user query falls into, or None."""
    lowered = text.lower()
    for category, patterns in ADVICE_REQUEST_PATTERNS.items():
        if any(re.search(p, lowered) for p in patterns):
            return category
    return None


def contains_advice(text: str) -> Optional[str]:
    """Return the first advice-shaped pattern found in outgoing text, or None."""
    lowered = text.lower()
    return next((p for p in ADVICE_CONTENT_PATTERNS if re.search(p, lowered)), None)


def is_controlled(*names: Optional[str]) -> bool:
    words = set()
    for name in names:
        if name:
            words.update(re.findall(r"[a-z]+", name.lower()))
    return not words.isdisjoint(CONTROLLED_SUBSTANCES)


def enforce_stock_policy(drug: Drug, result: StockResult) -> StockResult:
    """Controlled substances are never reported as in stock, whatever the adapter says."""
    if not drug.controlled:
        return result
    return StockResult(
        pharmacy_id=result.pharmacy_id, status="unknown", source="call_to_confirm",
        note=CONTROLLED_NOTE,
    )
