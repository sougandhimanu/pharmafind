import pytest

from app.tools.rxnorm import normalize_drug, parse_prescription, related_products


def test_parses_strength_quantity_and_form():
    drug = normalize_drug("Amoxicillin 500mg, 30 capsules")
    assert (drug.name, drug.strength, drug.quantity, drug.form) == ("amoxicillin", "500 mg", 30, "capsule")
    assert drug.matched and drug.rxcui == "723" and not drug.corrected


def test_misspelling_is_corrected_and_flagged():
    drug = normalize_drug("Amoxicilin 500")
    assert drug.matched and drug.name == "amoxicillin" and drug.corrected
    assert drug.strength == "500"  # no unit typed, none invented


def test_brand_name_maps_to_ingredient():
    drug = normalize_drug("Lipitor 20 mg")
    assert drug.name == "atorvastatin" and drug.strength == "20 mg"


def test_nonsense_is_not_matched():
    drug = normalize_drug("zzqxv")
    assert not drug.matched and drug.name is None


def test_near_miss_asks_instead_of_guessing():
    drug = normalize_drug("metfo")
    assert not drug.matched
    assert "metformin" in drug.suggestions


@pytest.mark.parametrize("text,qty", [("lisinopril 10mg #90", 90), ("cetirizine 10 mg 30 tabs", 30)])
def test_quantity_forms(text, qty):
    assert parse_prescription(text).quantity == qty


def test_alternatives_are_same_ingredient_only():
    drug = normalize_drug("semaglutide")
    products = related_products(drug)
    assert products and all(p.lower().startswith("semaglutide ") for p in products)
