import os
import sqlite3

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _all_stored_text() -> str:
    with sqlite3.connect(os.environ["PHARMAFIND_DB"]) as conn:
        rows = conn.execute("SELECT * FROM search_history").fetchall()
    return " ".join(str(v) for row in rows for v in row)


def test_searches_are_recorded_newest_first():
    client.get("/api/search", params={"q": "metformin 850", "zip": "10001"})
    client.get("/api/search", params={"q": "Amoxicillin 500mg, 30 capsules", "zip": "60601"})
    entries = client.get("/api/history").json()
    assert [e["drug_name"] for e in entries] == ["amoxicillin", "metformin"]
    first = entries[0]
    assert (first["strength"], first["quantity"], first["form"]) == ("500 mg", 30, "capsule")
    assert first["outcome"] == "ok" and first["pharmacy_count"] > 0
    assert first["location_label"].startswith("60601")


def test_raw_query_text_is_never_stored():
    client.get("/api/search", params={"q": "amoxicillin 500mg for Jane Example DOB 1980", "zip": "10001"})
    client.get("/api/search", params={"q": "How much should I take for my back pain?", "zip": "10001"})
    stored = _all_stored_text()
    for secret in ("Jane", "Example", "1980", "back pain", "How much"):
        assert secret not in stored
    refused = client.get("/api/history").json()[0]
    assert refused["outcome"] == "refused" and refused["refusal_category"] == "dosing"


def test_device_coordinates_are_not_stored():
    client.get("/api/search", params={"q": "amoxicillin", "lat": 41.8781, "lon": -87.6298})
    stored = _all_stored_text()
    assert "41.8781" not in stored and "-87.6298" not in stored


def test_errors_are_recorded_and_history_can_be_cleared():
    client.get("/api/search", params={"q": "amoxicillin", "zip": "abc"})
    assert client.get("/api/history").json()[0]["outcome"] == "error:invalid_zip"
    assert client.delete("/api/history").json()["deleted"] == 1
    assert client.get("/api/history").json() == []
