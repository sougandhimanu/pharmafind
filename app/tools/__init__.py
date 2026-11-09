"""Network tools. All third-party access lives in this package."""
import json
import os
import ssl
from functools import cache
from pathlib import Path
from typing import Any

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USER_AGENT = "PharmaFind/0.1 (prescription pharmacy finder demo)"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class ToolError(Exception):
    """A tool could not get an answer. Message is safe to show to the user."""


def is_offline() -> bool:
    return os.environ.get("PHARMAFIND_OFFLINE", "").strip() not in ("", "0", "false")


@cache
def load_json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def http_client() -> httpx.Client:
    # OS trust store rather than certifi: works behind corporate/AV TLS inspection.
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
                        verify=ssl.create_default_context())
