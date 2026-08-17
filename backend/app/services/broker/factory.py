"""Broker factory — PAPER mode always returns PaperBroker."""
from __future__ import annotations

from app.core.config import get_settings
from app.core.safety import current_mode_label, live_orders_allowed
from app.services.broker.base import BrokerInterface
from app.services.broker.live_broker import LiveBroker
from app.services.broker.paper_broker import PaperBroker


def get_broker(
    *,
    slippage_bps: float = 5.0,
    brokerage_per_order: float = 20.0,
    stt_rate: float = 0.00025,
    exchange_rate: float = 0.0000325,
    gst_rate: float = 0.18,
    sebi_rate: float = 0.000001,
    stamp_duty_rate: float = 0.00015,
    confirmation_token: str | None = None,
) -> BrokerInterface:
    """Strategy / order manager must use this factory.

    In PAPER mode (default), LiveBroker is never returned.
    """
    settings = get_settings()
    mode = current_mode_label()

    if mode == "PAPER" or not live_orders_allowed():
        return PaperBroker(
            slippage_bps=slippage_bps,
            brokerage_per_order=brokerage_per_order,
            stt_rate=stt_rate,
            exchange_rate=exchange_rate,
            gst_rate=gst_rate,
            sebi_rate=sebi_rate,
            stamp_duty_rate=stamp_duty_rate,
        )

    # LIVE path — still gated; week-1 keeps live_trading_enabled=false
    return LiveBroker(confirmation_token=confirmation_token)


def assert_no_live_orders_in_paper(broker: BrokerInterface) -> None:
    if get_settings().is_paper_mode and broker.is_live:
        raise RuntimeError("Safety violation: LiveBroker selected while PAPER MODE active")
