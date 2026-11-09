import httpx
import pytest


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Every test runs offline with a throwaway history DB; real network calls fail loudly."""
    monkeypatch.setenv("PHARMAFIND_OFFLINE", "1")
    monkeypatch.setenv("PHARMAFIND_DB", str(tmp_path / "history.db"))

    def no_network(*_args, **_kwargs):
        raise AssertionError("tests must not touch the network")

    # Patch the real transport, not Client, so FastAPI's in-process TestClient still works.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
