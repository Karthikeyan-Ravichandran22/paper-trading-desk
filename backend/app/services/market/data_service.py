"""Market data service — Angel One live or clearly-marked demo feed.

Demo data is synthetic for development when Angel One is not configured.
It is labelled DEMO so it is never confused with live broker prices.
"""
from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import pandas as pd

from app.core.config import get_settings
from app.core.timeutil import ist_now, utc_now
from app.services.broker.angel_one import angel_client
from app.services.market.session import is_market_open, market_status


TF_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "1d": 1440,
}


# Demo base prices (illustrative INR levels)
DEMO_BASE = {
    "NIFTY": 19850.0,
    "BANKNIFTY": 44800.0,
    "RELIANCE": 2950.0,
    "TCS": 4120.0,
    "INFY": 1850.0,
}


class MarketDataService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._ticks: dict[str, dict[str, Any]] = {}
        self._candles: dict[tuple[str, str], pd.DataFrame] = {}
        self._subscribers: list[Callable] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_tick_at: Optional[datetime] = None
        self._data_status = "INIT"
        self._ws_status = "DISCONNECTED"
        self._source = "DEMO" if self.settings.use_demo_market_data or not angel_client.is_configured else "ANGEL_ONE"

    @property
    def source(self) -> str:
        return self._source

    def status(self) -> dict[str, Any]:
        return {
            "source": self._source,
            "data_status": self._data_status,
            "websocket": self._ws_status,
            "last_tick": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "market": market_status(),
            "angel_one": angel_client.status(),
            "stale": self._is_stale(),
        }

    def _is_stale(self) -> bool:
        if not self._last_tick_at:
            return True
        age = (utc_now() - self._last_tick_at).total_seconds()
        return age > 30

    def subscribe(self, callback: Callable) -> None:
        self._subscribers.append(callback)

    async def _emit(self, event: str, payload: dict) -> None:
        for cb in list(self._subscribers):
            try:
                result = cb(event, payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    def get_ltp(self, symbol: str) -> Optional[float]:
        tick = self._ticks.get(symbol.upper())
        return float(tick["ltp"]) if tick else None

    def get_tick(self, symbol: str) -> Optional[dict]:
        return self._ticks.get(symbol.upper())

    def get_watchlist_quotes(self, symbols: list[str]) -> list[dict]:
        out = []
        for s in symbols:
            t = self._ticks.get(s.upper())
            if t:
                out.append(t)
            else:
                out.append(
                    {
                        "symbol": s.upper(),
                        "ltp": None,
                        "change": 0,
                        "change_pct": 0,
                        "volume": 0,
                        "source": self._source,
                    }
                )
        return out

    def get_candles(self, symbol: str, timeframe: str = "5m", limit: int = 300) -> pd.DataFrame:
        key = (symbol.upper(), timeframe)
        df = self._candles.get(key)
        if df is None or df.empty:
            df = self._generate_history(symbol.upper(), timeframe, limit)
            self._candles[key] = df
        return df.tail(limit).copy()

    def _generate_history(self, symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
        """Synthetic OHLCV clearly marked as DEMO source — for offline paper testing."""
        base = DEMO_BASE.get(symbol, 1000.0)
        minutes = TF_MINUTES.get(timeframe, 5)
        now = ist_now().replace(second=0, microsecond=0)
        # Align to timeframe
        now = now - timedelta(minutes=now.minute % minutes)
        rows = []
        price = base * (1 + random.uniform(-0.02, 0.02))
        rng = random.Random(hash(symbol) % 10_000)
        for i in range(bars, 0, -1):
            ts = now - timedelta(minutes=minutes * i)
            drift = rng.uniform(-0.0015, 0.0018)
            open_p = price
            close_p = max(0.01, open_p * (1 + drift))
            high_p = max(open_p, close_p) * (1 + rng.uniform(0, 0.001))
            low_p = min(open_p, close_p) * (1 - rng.uniform(0, 0.001))
            vol = rng.uniform(50_000, 500_000)
            rows.append(
                {
                    "ts": ts.astimezone(timezone.utc),
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "close": round(close_p, 2),
                    "volume": round(vol, 0),
                    "symbol": symbol,
                    "exchange": "NSE",
                    "timeframe": timeframe,
                    "source": "DEMO",
                }
            )
            price = close_p
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.set_index("ts")
        # Seed LTP
        if not df.empty:
            last = df.iloc[-1]
            self._ticks[symbol] = {
                "symbol": symbol,
                "exchange": "NSE",
                "ltp": float(last["close"]),
                "open": float(last["open"]),
                "high": float(last["high"]),
                "low": float(last["low"]),
                "change": round(float(last["close"]) - float(df.iloc[0]["open"]), 2),
                "change_pct": round(
                    100 * (float(last["close"]) - float(df.iloc[0]["open"])) / float(df.iloc[0]["open"]),
                    2,
                ),
                "volume": float(last["volume"]),
                "source": "DEMO",
                "ts": utc_now().isoformat(),
            }
            self._last_tick_at = utc_now()
        return df

    def _advance_demo_tick(self, symbol: str, timeframe: str = "5m") -> None:
        key = (symbol, timeframe)
        df = self._candles.get(key)
        if df is None or df.empty:
            df = self._generate_history(symbol, timeframe, 200)
            self._candles[key] = df
            return

        last = df.iloc[-1]
        ltp = float(last["close"])
        noise = random.uniform(-0.0008, 0.0008)
        # Mild mean reversion toward demo base
        base = DEMO_BASE.get(symbol, ltp)
        noise += 0.0001 * math.tanh((base - ltp) / base)
        new_price = max(0.01, ltp * (1 + noise))
        now = utc_now()
        minutes = TF_MINUTES.get(timeframe, 5)
        last_ts = df.index[-1]
        if isinstance(last_ts, pd.Timestamp):
            last_ts = last_ts.to_pydatetime()
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)

        # Update forming candle or append
        candle_start = now.replace(second=0, microsecond=0)
        minute_bucket = (candle_start.minute // minutes) * minutes
        candle_start = candle_start.replace(minute=minute_bucket)

        if candle_start <= last_ts.replace(second=0, microsecond=0):
            # update last bar
            df.loc[df.index[-1], "close"] = round(new_price, 2)
            df.loc[df.index[-1], "high"] = max(float(df.iloc[-1]["high"]), new_price)
            df.loc[df.index[-1], "low"] = min(float(df.iloc[-1]["low"]), new_price)
            df.loc[df.index[-1], "volume"] = float(df.iloc[-1]["volume"]) + random.uniform(100, 2000)
        else:
            new_row = pd.DataFrame(
                [
                    {
                        "open": round(ltp, 2),
                        "high": round(max(ltp, new_price), 2),
                        "low": round(min(ltp, new_price), 2),
                        "close": round(new_price, 2),
                        "volume": random.uniform(1000, 5000),
                        "symbol": symbol,
                        "exchange": "NSE",
                        "timeframe": timeframe,
                        "source": "DEMO",
                    }
                ],
                index=[candle_start],
            )
            df = pd.concat([df, new_row])
            if len(df) > 500:
                df = df.iloc[-500:]
            self._candles[key] = df

        day_open = float(df.iloc[max(0, len(df) - 78)]["open"]) if len(df) else new_price
        self._ticks[symbol] = {
            "symbol": symbol,
            "exchange": "NSE",
            "ltp": round(new_price, 2),
            "change": round(new_price - day_open, 2),
            "change_pct": round(100 * (new_price - day_open) / day_open, 2) if day_open else 0,
            "volume": float(df.iloc[-1]["volume"]),
            "source": "DEMO",
            "ts": now.isoformat(),
        }
        self._last_tick_at = now
        self._data_status = "LIVE" if is_market_open() or self._source == "DEMO" else "IDLE"
        self._ws_status = "CONNECTED"

    async def start(self, symbols: list[str], timeframe: str = "5m") -> None:
        if self._running:
            return
        self._running = True
        for s in symbols:
            self.get_candles(s, timeframe, 250)
        self._data_status = "LIVE"
        self._ws_status = "CONNECTED"
        self._task = asyncio.create_task(self._loop(symbols, timeframe))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self._ws_status = "DISCONNECTED"
        self._data_status = "STOPPED"

    async def _loop(self, symbols: list[str], timeframe: str) -> None:
        while self._running:
            try:
                if self._source == "DEMO" or not angel_client.is_connected:
                    for s in symbols:
                        self._advance_demo_tick(s.upper(), timeframe)
                        await self._emit("tick", self._ticks[s.upper()])
                else:
                    # Live Angel One LTP path (when authenticated)
                    for s in symbols:
                        tick = self._ticks.get(s.upper())
                        token = (tick or {}).get("token", "")
                        if token:
                            ltp = await angel_client.get_ltp("NSE", s, token)
                            if ltp:
                                self._ticks[s.upper()] = {
                                    **(tick or {}),
                                    "symbol": s.upper(),
                                    "ltp": ltp,
                                    "source": "ANGEL_ONE",
                                    "ts": utc_now().isoformat(),
                                }
                                self._last_tick_at = utc_now()
                                await self._emit("tick", self._ticks[s.upper()])
                    self._data_status = "LIVE"
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception:
                self._data_status = "ERROR"
                self._ws_status = "RECONNECTING"
                await asyncio.sleep(2.0)


market_data_service = MarketDataService()
