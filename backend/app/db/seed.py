"""Database seed — paper portfolio, SORE strategy, watchlist, 7-day experiment."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.timeutil import utc_now
from app.db import models
from app.db.session import SessionLocal
from app.services.strategy.sore_scalper import (
    DEFAULT_PARAMS,
    SORE_PINE_SOURCE,
    SoreScalperPro,
)


async def seed_database() -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        # Portfolio
        result = await db.execute(select(models.Portfolio).limit(1))
        if not result.scalar_one_or_none():
            db.add(
                models.Portfolio(
                    name="Paper Portfolio",
                    mode="PAPER",
                    starting_capital=settings.default_starting_capital,
                    cash=settings.default_starting_capital,
                    equity=settings.default_starting_capital,
                    peak_equity=settings.default_starting_capital,
                    slippage_bps=settings.default_slippage_bps,
                    brokerage_per_order=settings.default_brokerage_per_order,
                )
            )

        # Strategy
        result = await db.execute(select(models.StrategyConfig).limit(1))
        if not result.scalar_one_or_none():
            report = SoreScalperPro.validate(SORE_SCALPER_PINE, DEFAULT_PARAMS)
            db.add(
                models.StrategyConfig(
                    name=SoreScalperPro.NAME,
                    version=SoreScalperPro.VERSION,
                    pine_source=SORE_SCALPER_PINE,
                    parameters=DEFAULT_PARAMS,
                    symbols=["NIFTY", "BANKNIFTY", "RELIANCE", "TCS"],
                    exchange="NSE",
                    timeframe="5m",
                    is_active=True,
                    validation_status="PASS" if report.passed else "FAIL",
                    validation_report={
                        "checks": report.checks,
                        "warnings": report.warnings,
                    },
                    unsupported_features=report.unsupported,
                )
            )

        # Watchlist
        result = await db.execute(select(models.WatchlistItem).limit(1))
        if not result.scalar_one_or_none():
            for i, sym in enumerate(["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "INFY"]):
                db.add(models.WatchlistItem(symbol=sym, exchange="NSE", sort_order=i))

        # 7-day experiment
        result = await db.execute(select(models.PaperExperiment).limit(1))
        if not result.scalar_one_or_none():
            now = utc_now()
            db.add(
                models.PaperExperiment(
                    name="7-DAY PAPER TEST",
                    strategy_name=SoreScalperPro.NAME,
                    symbols=["NIFTY", "BANKNIFTY", "RELIANCE", "TCS"],
                    timeframe="5m",
                    starting_capital=settings.default_starting_capital,
                    status="RUNNING",
                    started_at=now,
                    ends_at=now + timedelta(days=7),
                )
            )

        # System settings
        result = await db.execute(
            select(models.SystemSetting).where(models.SystemSetting.key == "trading_mode")
        )
        if not result.scalar_one_or_none():
            db.add(
                models.SystemSetting(
                    key="trading_mode",
                    value={
                        "mode": "PAPER",
                        "live_trading_enabled": False,
                        "live_locked_reason": "Complete 7-day paper test and human review first",
                    },
                )
            )

        db.add(
            models.AuditLog(
                category="SYSTEM",
                action="DATABASE_SEEDED",
                detail={"mode": "PAPER", "strategy": SoreScalperPro.NAME},
            )
        )
        await db.commit()


# Full user-provided Pine (truncated storage of visual sections OK; logic ported)
SORE_SCALPER_PINE = '''//@version=6
indicator("SORE Scalper Pro — Automation & Visual Edition v7.60", overlay=true, max_labels_count=500, max_lines_count=500)

// SECTION 1 — INPUTS
emaLen    = input.int(34, "Base EMA Length")
htAmp     = input.int(2,  "HalfTrend Amplitude")
stLen     = input.int(10, "Supertrend ATR Len")
stMult    = input.float(3.0,"Supertrend Mult")
fastOsc   = input.int(12, "Oscillator Fast")
slowOsc   = input.int(26, "Oscillator Slow")
sigOsc    = input.int(9,  "Oscillator Signal")
maFastLen = input.int(13, "EMA Fast")
maSlowLen = input.int(34, "EMA Slow")
atrLen    = input.int(14, "ATR Len")
rsiLen    = input.int(14, "RSI Len")
minMTF    = input.int(4,  "Min MTFs (out of 11)")
minEaF    = input.int(2,  "Min EA Filters (4)")
slATR           = input.float(1.5, "SL ATR Mult")
baseTp1ATR      = input.float(1.0, "Base TP1 ATR Mult")
baseTp2ATR      = input.float(2.5, "Base TP2 ATR Mult")
useDynamicVol   = input.bool(true,  "Auto-Adjust TP based on Volatility?")
use1mExit       = input.bool(true,  "Exit on 1m Trend Flip?")
useExit         = input.bool(false, "Early Exit on Stoch Flip?")

// CORE: EMA, Supertrend, HalfTrend, Oscillator, EA filters, Neon candles, MTF gate
// ENTRY: longCond / shortCond with tradeState flat-only
// EXIT: SL, 1m trend flip, trend reverse, optional stoch
// Full executable port: app.services.strategy.sore_scalper.SoreScalperPro
'''
