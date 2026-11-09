"""FastAPI app: GET /api/search and the one-page UI."""
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import history
from app.guardrails import advice_request_category
from app.models import SearchResponse
from app.pipeline import DEFAULT_RADIUS_KM, SearchError, search
from app.tools import is_offline
from app.tools.stock import IS_SIMULATED

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="PharmaFind", version="0.1.0")


@app.exception_handler(SearchError)
async def _search_error(_, exc: SearchError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content={"error": exc.code, "message": exc.message})


@app.get("/api/search", response_model=SearchResponse)
def api_search(
    q: str = Query("", max_length=200, description="Medicine as written on the prescription"),
    zip: Optional[str] = Query(None, max_length=10),
    lat: Optional[float] = Query(None, ge=-90, le=90),
    lon: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: float = Query(DEFAULT_RADIUS_KM, gt=0, le=25),
) -> SearchResponse:
    try:
        resp = search(q, zip_code=zip, lat=lat, lon=lon, radius_km=radius_km)
    except SearchError as exc:
        history.record_error(exc.code)
        raise
    category = advice_request_category(q) if resp.status == "refused" else None
    history.record_response(resp, refusal_category=category)
    return resp


@app.get("/api/history", response_model=list[history.HistoryEntry])
def api_history(limit: int = Query(20, ge=1, le=200)) -> list[history.HistoryEntry]:
    return history.recent(limit)


@app.delete("/api/history")
def api_clear_history() -> dict:
    return {"deleted": history.clear()}


@app.get("/api/status")
def api_status() -> dict:
    return {"offline": is_offline(), "stock_is_simulated": IS_SIMULATED}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
