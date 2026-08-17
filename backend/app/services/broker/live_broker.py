"""LiveBroker — intentionally disabled for paper-trading phase.

Even constructing an order call raises unless LIVE_TRADING_ENABLED=true
AND trading_mode=LIVE AND an explicit confirmation token is provided.
"""
from __future__ import annotations

from app.core.safety import LiveTradingBlockedError, live_orders_allowed
from app.services.broker.base import (
    BrokerInterface,
    BrokerOrderRequest,
    BrokerOrderResult,
    OrderStatus,
)


class LiveBroker(BrokerInterface):
    """Stub live broker. Order placement is HARD-DISABLED by default."""

    def __init__(self, confirmation_token: str | None = None):
        self.confirmation_token = confirmation_token

    @property
    def name(self) -> str:
        return "LiveBroker"

    @property
    def is_live(self) -> bool:
        return True

    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        # CRITICAL SAFETY: never reach Angel One placeOrder during paper phase
        if not live_orders_allowed():
            raise LiveTradingBlockedError(
                "LIVE MODE is disabled. Paper-trading experiment cannot place real orders. "
                "No Angel One order API was called."
            )
        if self.confirmation_token != "I_UNDERSTAND_LIVE_ORDERS":
            raise LiveTradingBlockedError(
                "Live order requires explicit confirmation token. No Angel One order API was called."
            )
        # Even when enabled later, this must go through Angel One client —
        # intentionally not implemented during week-1 paper phase.
        return BrokerOrderResult(
            success=False,
            status=OrderStatus.REJECTED,
            broker_name=self.name,
            rejection_reason=(
                "Live order placement is not implemented in this build. "
                "Complete the 7-day paper test and human review first."
            ),
        )

    async def cancel_order(self, order_id: str) -> bool:
        if not live_orders_allowed():
            raise LiveTradingBlockedError("LIVE MODE is disabled.")
        return False

    async def place_order_via_angel(self, *_args, **_kwargs):
        """Explicitly blocked path — proves tests cannot hit live order API."""
        raise LiveTradingBlockedError(
            "Angel One live order API is blocked. PAPER MODE active."
        )
