import pytest

from app import agents, guardrails
from app.models import Alternatives, Drug, SearchResponse, StockResult
from app.pipeline import search


@pytest.mark.parametrize("query", [
    "How much should I take?",
    "How often can I take ibuprofen with it?",
    "Can I swap this for something cheaper?",
    "Is semaglutide safe with my other pills?",
    "amoxicillin 500mg what dose for a child",
    "does metformin interact with alcohol",
    "what should i take for a headache",
])
def test_advice_requests_are_refused(query):
    resp = search(query, "10001")
    assert resp.status == "refused"
    assert resp.results == []
    assert "pharmacist or prescriber" in resp.message


@pytest.mark.parametrize("query", ["amoxicillin 500mg", "metformin 850", "Lipitor 20 mg", "insulin glargine pen"])
def test_ordinary_prescriptions_are_not_refused(query):
    assert guardrails.advice_request_category(query) is None


@pytest.mark.parametrize("query", ["oxycodone 5mg", "Adderall", "Xanax 0.5mg", "zolpidem", "Aderall 20mg"])
def test_controlled_substances_never_in_stock(query):
    resp = search(query, "10001")
    assert resp.drug.controlled
    assert resp.results, "controlled search should still list pharmacies to call"
    for r in resp.results:
        assert r.stock.status == "unknown"
        assert r.stock.source == "call_to_confirm"


@pytest.mark.parametrize("status", ["in_stock", "low", "out_of_stock", "unknown"])
def test_stock_policy_overrides_any_adapter_status(status):
    drug = Drug(query="oxycodone", name="oxycodone", matched=True, controlled=True)
    raw = StockResult(pharmacy_id="p1", status=status, source="mock")
    enforced = guardrails.enforce_stock_policy(drug, raw)
    assert (enforced.status, enforced.source) == ("unknown", "call_to_confirm")


@pytest.mark.parametrize("text", [
    "Take 2 tablets every 6 hours.",
    "You can switch to ibuprofen instead.",
    "It's safe with alcohol.",
    "Use 1 capsule 3 times a day.",
])
def test_safety_reviewer_blocks_advice(text):
    draft = SearchResponse(status="ok", message=text, stock_is_simulated=True, disclaimer=guardrails.DISCLAIMER)
    assert not agents.safety_review(draft).approved


def test_safety_reviewer_blocks_alternatives_without_disclaimer():
    draft = SearchResponse(
        status="ok", message="ok", stock_is_simulated=True, disclaimer=guardrails.DISCLAIMER,
        alternatives=Alternatives(items=["amoxicillin 250 MG Oral Capsule"], disclaimer=""),
    )
    assert not agents.safety_review(draft).approved


def test_own_fixed_messages_pass_the_reviewer():
    for text in (guardrails.REFUSAL_MESSAGE, guardrails.DISCLAIMER, guardrails.CONTROLLED_NOTE,
                 guardrails.SAFE_FALLBACK_MESSAGE):
        assert guardrails.contains_advice(text) is None, text


def test_every_response_is_labelled_simulated():
    for q in ("amoxicillin", "zzqxv", "How much should I take?"):
        resp = search(q, "10001")
        assert resp.stock_is_simulated is True
        assert "simulated" in resp.disclaimer.lower()
