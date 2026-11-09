from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import agents
from app.main import app
from app.models import Pharmacy, PharmacyStock, StockResult
from app.pipeline import SearchError, search
from app.tools import ToolError
from app.tools.stock import check_stock


def _item(pid, status, km):
    pharmacy = Pharmacy(id=pid, name=pid, lat=0, lon=0, distance_km=km)
    return PharmacyStock(pharmacy=pharmacy, stock=StockResult(pharmacy_id=pid, status=status, source="mock"))


def test_ranker_orders_by_status_then_distance():
    found = [_item("a", "out_of_stock", 0.1), _item("b", "unknown", 0.2), _item("c", "low", 0.3),
             _item("d", "in_stock", 2.0), _item("e", "in_stock", 1.0)]
    ranked = agents.rank(found)
    assert [r.pharmacy.id for r in ranked] == ["e", "d", "c", "b", "a"]
    assert [r.rank for r in ranked] == [1, 2, 3, 4, 5]


def test_mock_stock_is_deterministic():
    pharmacy = Pharmacy(id="sample-1", name="x", lat=0, lon=0, distance_km=0)
    drug = search("metformin", "10001").drug
    assert check_stock(pharmacy, drug) == check_stock(pharmacy, drug)


def test_valid_search_returns_ranked_sample_pharmacies():
    resp = search("metformin 850", "10001")
    assert resp.status == "ok" and resp.pharmacy_source == "sample"
    assert resp.results and resp.results[0].stock.status == "in_stock"
    assert all(r.pharmacy.name.endswith("(sample)") for r in resp.results)
    distances = [r.pharmacy.distance_km for r in resp.results]
    assert max(distances) <= 5.0


def test_nothing_in_stock_lists_alternatives_with_disclaimer():
    resp = search("semaglutide", "10001")
    assert all(r.stock.status == "out_of_stock" for r in resp.results)
    assert "none" in resp.message.lower()
    assert resp.alternatives and resp.alternatives.items
    assert "pharmacist or prescriber" in resp.alternatives.disclaimer


def test_device_location_works_without_zip():
    resp = search("amoxicillin", lat=41.0, lon=-87.0)
    assert resp.status == "ok" and resp.location.label == "Your current location"


@pytest.mark.parametrize("zip_code,code", [(None, "missing_location"), ("abc", "invalid_zip"),
                                            ("99999", "location_lookup_failed")])
def test_location_errors(zip_code, code):
    with pytest.raises(SearchError) as err:
        search("amoxicillin", zip_code)
    assert err.value.code == code


def test_pharmacy_lookup_failure_is_clean_and_fabricates_nothing():
    with patch("app.agents.find_pharmacies", side_effect=ToolError("Pharmacy lookup is unavailable")):
        with pytest.raises(SearchError) as err:
            search("amoxicillin", "10001")
    assert err.value.code == "pharmacy_lookup_failed" and err.value.http_status == 502


def test_query_text_is_not_logged(caplog):
    caplog.set_level("INFO")
    search("Amoxicillin 500mg, 30 capsules for Jane Example", "10001")
    assert "Jane" not in caplog.text and "30 capsules" not in caplog.text


def test_api_search_and_errors():
    client = TestClient(app)
    ok = client.get("/api/search", params={"q": "amoxicillin", "zip": "10001"})
    assert ok.status_code == 200 and ok.json()["stock_is_simulated"] is True
    assert client.get("/api/search", params={"q": "amoxicillin"}).status_code == 400
    assert client.get("/api/search", params={"q": "amoxicillin", "zip": "abc"}).status_code == 422
    assert client.get("/").status_code == 200
