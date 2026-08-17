"""Angel One SmartAPI client — market data & auth only during paper phase.

Order-placement methods exist as stubs that raise LiveTradingBlockedError
so accidental calls cannot send real orders.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
import pyotp

from app.core.config import get_settings
from app.core.safety import LiveTradingBlockedError, live_orders_allowed

logger = logging.getLogger(__name__)

SMARTAPI_BASE = "https://apiconnect.angelone.in"


class AngelOneClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.jwt_token: str = self.settings.angel_jwt_token
        self.feed_token: str = self.settings.angel_feed_token
        self.refresh_token: str = self.settings.angel_refresh_token
        self._connected = False
        self._last_error: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.angel_api_key
            and self.settings.angel_client_code
            and self.settings.angel_password
            and self.settings.angel_totp_secret
        )

    @property
    def is_connected(self) -> bool:
        return self._connected and bool(self.jwt_token)

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    def _generate_totp(self) -> str:
        secret = self.settings.angel_totp_secret.strip().replace(" ", "")
        return pyotp.TOTP(secret).now()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "100.52.140.165",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self.settings.angel_api_key,
        }

    async def login(self, totp: str | None = None) -> dict[str, Any]:
        # Always reload settings so freshly saved .env values are picked up after restart
        self.settings = get_settings()
        if not self.is_configured:
            self._last_error = "Angel One credentials not configured"
            return {"status": False, "message": self._last_error}

        code = (totp or "").strip() or self._generate_totp()
        # Password/PIN/TOTP never logged
        payload = {
            "clientcode": self.settings.angel_client_code,
            "password": self.settings.angel_password,
            "totp": code,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{SMARTAPI_BASE}/rest/auth/angelbroking/user/v1/loginByPassword",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "X-UserType": "USER",
                        "X-SourceID": "WEB",
                        "X-ClientLocalIP": "127.0.0.1",
                        "X-ClientPublicIP": "100.52.140.165",
                        "X-MACAddress": "00:00:00:00:00:00",
                        "X-PrivateKey": self.settings.angel_api_key,
                    },
                )
                data = resp.json()
                if data.get("status") and data.get("data"):
                    self.jwt_token = data["data"].get("jwtToken", "")
                    self.feed_token = data["data"].get("feedToken", "")
                    self.refresh_token = data["data"].get("refreshToken", "")
                    self._connected = True
                    self._last_error = None
                    return {"status": True, "message": "Angel One authentication succeeded"}
                self._last_error = data.get("message", "Angel One authentication failed")
                self._connected = False
                # Never include raw response secrets
                return {"status": False, "message": self._last_error}
        except Exception as exc:
            self._last_error = f"Angel One authentication failed: {exc}"
            self._connected = False
            logger.exception("Angel One login error")
            return {"status": False, "message": self._last_error}


    async def get_ltp(self, exchange: str, symbol: str, token: str) -> Optional[float]:
        if not self.jwt_token:
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{SMARTAPI_BASE}/rest/secure/angelbroking/order/v1/getLtpData",
                    json={"exchange": exchange, "tradingsymbol": symbol, "symboltoken": token},
                    headers=self._headers(),
                )
                data = resp.json()
                if data.get("status") and data.get("data"):
                    return float(data["data"].get("ltp", 0))
        except Exception:
            logger.exception("LTP fetch failed")
        return None

    async def get_candle_data(
        self,
        exchange: str,
        symbol_token: str,
        interval: str,
        from_date: str,
        to_date: str,
    ) -> list[dict[str, Any]]:
        """Fetch historical OHLCV. Returns list of candle dicts."""
        if not self.jwt_token:
            return []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{SMARTAPI_BASE}/rest/secure/angelbroking/historical/v1/getCandleData",
                    json={
                        "exchange": exchange,
                        "symboltoken": symbol_token,
                        "interval": interval,
                        "fromdate": from_date,
                        "todate": to_date,
                    },
                    headers=self._headers(),
                )
                data = resp.json()
                candles = []
                if data.get("status") and data.get("data"):
                    for row in data["data"]:
                        # [timestamp, open, high, low, close, volume]
                        candles.append(
                            {
                                "ts": row[0],
                                "open": float(row[1]),
                                "high": float(row[2]),
                                "low": float(row[3]),
                                "close": float(row[4]),
                                "volume": float(row[5]) if len(row) > 5 else 0.0,
                            }
                        )
                return candles
        except Exception:
            logger.exception("Historical data fetch failed")
            return []

    async def place_order(self, *_args, **_kwargs) -> dict[str, Any]:
        """HARD BLOCK — never place real orders during paper phase."""
        if not live_orders_allowed():
            raise LiveTradingBlockedError(
                "Angel One placeOrder blocked: PAPER MODE active. "
                "No real order API call was made."
            )
        raise LiveTradingBlockedError(
            "Live order API not enabled in this build. Complete paper test first."
        )

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.is_configured,
            "connected": self.is_connected,
            "last_error": self._last_error,
            "live_orders": "DISABLED",
            "market_data_allowed": True,
        }


# Singleton for app lifespan
angel_client = AngelOneClient()
