"""Resolve Angel One instrument tokens (esp. MCX CRUDEOIL front-month)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

SCRIP_MASTER_URL = (
    "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
)

# In-memory cache
_CACHE: list[dict[str, Any]] | None = None
_CACHE_AT: float | None = None


async def load_scrip_master(force: bool = False) -> list[dict[str, Any]]:
    global _CACHE, _CACHE_AT
    import time

    if _CACHE is not None and not force and _CACHE_AT and time.time() - _CACHE_AT < 3600:
        return _CACHE
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(SCRIP_MASTER_URL)
            resp.raise_for_status()
            _CACHE = resp.json()
            _CACHE_AT = time.time()
            return _CACHE
    except Exception:
        logger.exception("Failed to download Angel One scrip master")
        return _CACHE or []


def _parse_expiry(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%d%b%Y").replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def resolve_instrument(
    symbol: str,
    exchange: str = "NSE",
) -> dict[str, Any]:
    """Resolve display symbol to Angel trading symbol + token.

    Special-case: CRUDEOIL / CRUDE on MCX → nearest CRUDEOIL*FUT contract.
    """
    sym = symbol.upper().strip().replace(" ", "")
    exch = exchange.upper().strip()

    # Aliases for crude oil continuous-style names from TradingView
    crude_aliases = {
        "CRUDEOIL",
        "CRUDEOIL1!",
        "CRUDEOIL1",
        "CRUDEFUT",
        "CRUDE",
        "MCX:CRUDEOIL1!",
        "MCX:CRUDEOIL",
    }
    if sym in crude_aliases or (sym.startswith("CRUDEOIL") and exch in ("MCX", "NSE")):
        exch = "MCX"
        master = await load_scrip_master()
        now = datetime.now(timezone.utc)
        candidates = []
        for row in master:
            if (row.get("exch_seg") or "").upper() != "MCX":
                continue
            rsym = (row.get("symbol") or "").upper()
            # Prefer full CRUDEOIL lot (100), not CRUDEOILM mini
            if not (rsym.startswith("CRUDEOIL") and rsym.endswith("FUT")):
                continue
            if rsym.startswith("CRUDEOILM"):
                continue
            exp = _parse_expiry(row.get("expiry") or "")
            if not exp:
                continue
            if exp.date() < now.date():
                continue
            candidates.append((exp, row))
        candidates.sort(key=lambda x: x[0])
        if candidates:
            exp, row = candidates[0]
            return {
                "symbol": "CRUDEOIL",
                "trading_symbol": row.get("symbol"),
                "exchange": "MCX",
                "token": str(row.get("token") or ""),
                "expiry": row.get("expiry"),
                "lot_size": int(row.get("lotsize") or 100),
                "name": row.get("name") or "CRUDEOIL",
                "instrument_type": row.get("instrumenttype") or "FUTCOM",
            }
        return {
            "symbol": "CRUDEOIL",
            "trading_symbol": "CRUDEOIL",
            "exchange": "MCX",
            "token": "",
            "lot_size": 100,
            "name": "CRUDEOIL",
            "warning": "Could not resolve front-month CRUDEOIL token from scrip master",
        }

    # Default equity-style passthrough
    return {
        "symbol": sym,
        "trading_symbol": sym if sym.endswith("-EQ") or "FUT" in sym else sym,
        "exchange": exch,
        "token": "",
        "lot_size": 1,
        "name": sym,
    }
