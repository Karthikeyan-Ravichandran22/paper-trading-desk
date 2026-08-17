"""Indian market session handling (NSE/BSE) — Asia/Kolkata."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.core.timeutil import ist_now

# Approximate NSE holidays 2025-2026 (extend as needed)
NSE_HOLIDAYS = {
    date(2025, 2, 26),
    date(2025, 3, 14),
    date(2025, 3, 31),
    date(2025, 4, 10),
    date(2025, 4, 14),
    date(2025, 4, 18),
    date(2025, 5, 1),
    date(2025, 8, 15),
    date(2025, 8, 27),
    date(2025, 10, 2),
    date(2025, 10, 21),
    date(2025, 10, 22),
    date(2025, 11, 5),
    date(2025, 12, 25),
    date(2026, 1, 26),
    date(2026, 3, 3),
    date(2026, 3, 26),
    date(2026, 3, 31),
    date(2026, 4, 3),
    date(2026, 4, 14),
    date(2026, 5, 1),
    date(2026, 8, 15),
    date(2026, 10, 2),
    date(2026, 10, 20),
    date(2026, 11, 8),
    date(2026, 12, 25),
}

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def is_holiday(d: date | None = None) -> bool:
    d = d or ist_now().date()
    return d in NSE_HOLIDAYS


def is_weekend(d: date | None = None) -> bool:
    d = d or ist_now().date()
    return d.weekday() >= 5


def is_market_open(now: datetime | None = None) -> bool:
    now = now or ist_now()
    d = now.date()
    if is_weekend(d) or is_holiday(d):
        return False
    t = now.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


def market_status(now: datetime | None = None) -> dict:
    now = now or ist_now()
    open_now = is_market_open(now)
    if is_weekend(now.date()):
        reason = "Weekend"
    elif is_holiday(now.date()):
        reason = "Market holiday"
    elif now.time() < MARKET_OPEN:
        reason = "Pre-open"
    elif now.time() > MARKET_CLOSE:
        reason = "Closed"
    else:
        reason = "Regular session"
    return {
        "exchange": "NSE/BSE",
        "status": "OPEN" if open_now else "CLOSED",
        "reason": reason,
        "ist": now.strftime("%Y-%m-%d %H:%M:%S"),
        "session": f"{MARKET_OPEN.strftime('%H:%M')}–{MARKET_CLOSE.strftime('%H:%M')} IST",
    }


def next_session_open(now: datetime | None = None) -> datetime:
    now = now or ist_now()
    d = now.date()
    candidate = datetime.combine(d, MARKET_OPEN, tzinfo=now.tzinfo)
    if now < candidate and not is_weekend(d) and not is_holiday(d):
        return candidate
    for i in range(1, 15):
        nd = d + timedelta(days=i)
        if not is_weekend(nd) and not is_holiday(nd):
            return datetime.combine(nd, MARKET_OPEN, tzinfo=now.tzinfo)
    return candidate
