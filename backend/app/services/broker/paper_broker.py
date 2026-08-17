"""PaperBroker — simulated fills only. Never calls Angel One order APIs."""
from __future__ import annotations

from app.core.timeutil import utc_now
from app.services.broker.base import (
    BrokerInterface,
    BrokerOrderRequest,
    BrokerOrderResult,
    OrderStatus,
)


class PaperBroker(BrokerInterface):
    def __init__(
        self,
        slippage_bps: float = 5.0,
        brokerage_per_order: float = 20.0,
        stt_rate: float = 0.00025,
        exchange_rate: float = 0.0000325,
        gst_rate: float = 0.18,
        sebi_rate: float = 0.000001,
        stamp_duty_rate: float = 0.00015,
    ):
        self.slippage_bps = slippage_bps
        self.brokerage_per_order = brokerage_per_order
        self.stt_rate = stt_rate
        self.exchange_rate = exchange_rate
        self.gst_rate = gst_rate
        self.sebi_rate = sebi_rate
        self.stamp_duty_rate = stamp_duty_rate

    @property
    def name(self) -> str:
        return "PaperBroker"

    @property
    def is_live(self) -> bool:
        return False

    def _apply_slippage(self, price: float, side: str) -> tuple[float, float]:
        slip = price * (self.slippage_bps / 10_000.0)
        if side == "BUY":
            return price + slip, slip
        return price - slip, slip

    def _calc_charges(self, turnover: float, side: str) -> float:
        brokerage = self.brokerage_per_order
        stt = turnover * self.stt_rate if side == "SELL" else 0.0
        exchange = turnover * self.exchange_rate
        sebi = turnover * self.sebi_rate
        stamp = turnover * self.stamp_duty_rate if side == "BUY" else 0.0
        gst = (brokerage + exchange) * self.gst_rate
        return brokerage + stt + exchange + sebi + stamp + gst

    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        if request.quantity <= 0:
            return BrokerOrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                broker_name=self.name,
                rejection_reason="Invalid quantity",
            )
        if request.price <= 0:
            return BrokerOrderResult(
                success=False,
                status=OrderStatus.REJECTED,
                broker_name=self.name,
                rejection_reason="Invalid price",
            )

        fill_price, slip = self._apply_slippage(request.price, request.side.value)
        turnover = fill_price * request.quantity
        charges = self._calc_charges(turnover, request.side.value)

        return BrokerOrderResult(
            success=True,
            status=OrderStatus.FILLED,
            fill_price=round(fill_price, 4),
            brokerage=self.brokerage_per_order,
            charges=round(charges - self.brokerage_per_order, 4),
            slippage=round(slip * request.quantity, 4),
            broker_name=self.name,
            filled_at=utc_now(),
            raw={
                "mode": "PAPER",
                "idempotency_key": request.idempotency_key,
                "note": "Simulated fill — not a real broker order",
            },
        )

    async def cancel_order(self, order_id: str) -> bool:
        return True
