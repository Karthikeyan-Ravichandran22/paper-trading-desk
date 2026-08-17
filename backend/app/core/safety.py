"""Trading mode safety — hard gate against live orders."""
from enum import Enum

from app.core.config import get_settings


class TradingMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class LiveTradingBlockedError(RuntimeError):
    """Raised when any code path attempts a live order while LIVE is disabled."""


def assert_paper_mode_or_raise(context: str = "") -> None:
    """Hard safety check. LIVE order APIs must never be reachable in paper phase."""
    settings = get_settings()
    if settings.is_paper_mode or not settings.live_trading_enabled:
        return
    # Even if somehow LIVE is requested during week-1, block by default
    raise LiveTradingBlockedError(
        f"Live trading is disabled for the paper-trading experiment. Context: {context}"
    )


def live_orders_allowed() -> bool:
    """LIVE order placement requires BOTH flags. Default: False."""
    settings = get_settings()
    return (
        settings.live_trading_enabled
        and settings.trading_mode == "LIVE"
        and not settings.is_paper_mode
    )


def current_mode_label() -> str:
    settings = get_settings()
    if settings.is_paper_mode or not settings.live_trading_enabled:
        return "PAPER"
    return "LIVE"
