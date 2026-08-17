"""Risk engine — hard checks before any paper order."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.core.timeutil import ist_now
from app.services.market.session import is_market_open


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""


class RiskEngine:
    def __init__(
        self,
        max_position_size: float = 50_000.0,
        max_daily_loss: float = 5_000.0,
        max_open_positions: int = 3,
        require_session: bool = False,  # demo mode may run outside session
        allow_demo_outside_session: bool = True,
    ):
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.max_open_positions = max_open_positions
        self.require_session = require_session
        self.allow_demo_outside_session = allow_demo_outside_session
        self._seen_keys: set[str] = set()
        self._daily_realized = 0.0
        self._daily_date: Optional[str] = None

    def reset_day_if_needed(self) -> None:
        today = ist_now().strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_date = today
            self._daily_realized = 0.0

    def record_realized(self, pnl: float) -> None:
        self.reset_day_if_needed()
        self._daily_realized += pnl

    def validate(
        self,
        *,
        symbol: str,
        signal_type: str,
        price: float,
        quantity: int,
        idempotency_key: str,
        strategy_active: bool,
        open_positions: int,
        has_open_position_for_symbol: bool,
        available_cash: float,
        market_data_valid: bool,
        data_source: str = "DEMO",
        now: datetime | None = None,
    ) -> RiskDecision:
        self.reset_day_if_needed()

        if not market_data_valid:
            return RiskDecision(False, "Invalid or stale market data")
        if not symbol:
            return RiskDecision(False, "Invalid symbol")
        if not strategy_active:
            return RiskDecision(False, "Strategy is not active")
        if signal_type not in ("BUY", "SELL", "EXIT"):
            return RiskDecision(False, f"Invalid signal type: {signal_type}")
        if price is None or price <= 0:
            return RiskDecision(False, "Invalid market data — price")
        if quantity <= 0 and signal_type in ("BUY", "SELL"):
            return RiskDecision(False, "Invalid quantity")

        if idempotency_key in self._seen_keys:
            return RiskDecision(False, "Duplicate signal ignored")

        if self.require_session or (data_source != "DEMO" and not self.allow_demo_outside_session):
            if not is_market_open(now):
                return RiskDecision(False, "Market session closed — ordinary signals blocked")

        if abs(self._daily_realized) >= self.max_daily_loss and self._daily_realized < 0:
            return RiskDecision(False, "Maximum daily loss limit exceeded")

        if signal_type in ("BUY", "SELL") and not has_open_position_for_symbol:
            if open_positions >= self.max_open_positions:
                return RiskDecision(False, "Maximum open positions exceeded")
            notional = price * quantity
            if notional > self.max_position_size:
                return RiskDecision(False, "Maximum position size exceeded")
            if signal_type == "BUY" and notional > available_cash:
                return RiskDecision(False, "Insufficient simulated capital")

        if signal_type in ("BUY", "SELL") and has_open_position_for_symbol:
            # Flat-only entries per Pine tradeState == 0
            return RiskDecision(False, "Position already open for symbol")

        return RiskDecision(True, "OK")

    def mark_seen(self, idempotency_key: str) -> None:
        self._seen_keys.add(idempotency_key)
        # Bound memory
        if len(self._seen_keys) > 10_000:
            self._seen_keys = set(list(self._seen_keys)[-5_000:])
