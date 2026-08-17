"""Strategy evaluation loop — market data → candles → SORE → signals → paper orders."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utc_now, ensure_utc
from app.db import models
from app.db.session import SessionLocal
from app.services.market.data_service import market_data_service
from app.services.paper.order_manager import OrderManager
from app.services.analytics.metrics import refresh_portfolio_marks
from app.services.risk.engine import RiskEngine
from app.services.strategy.sore_scalper import SoreScalperPro

logger = logging.getLogger(__name__)


class SignalEngine:
    def __init__(self) -> None:
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_eval: Optional[str] = None
        self._last_signal: Optional[dict] = None
        self._strategy_status = "IDLE"
        self._notifications: list[dict] = []
        self.order_manager = OrderManager(RiskEngine())
        self._strategy = SoreScalperPro()
        self._last_candle_keys: set[str] = set()

    def status(self) -> dict[str, Any]:
        return {
            "strategy": self._strategy_status,
            "last_evaluation": self._last_eval,
            "last_signal": self._last_signal,
            "paper_engine": "ACTIVE",
            "live_trading": "DISABLED",
            "notifications": self._notifications[-20:],
        }

    def pop_notifications(self) -> list[dict]:
        notes = list(self._notifications)
        return notes

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._strategy_status = "RUNNING"
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        self._strategy_status = "STOPPED"
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.evaluate_once()
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Strategy evaluation failed")
                self._strategy_status = "ERROR"
                await asyncio.sleep(3.0)
                self._strategy_status = "RUNNING"

    async def evaluate_once(self) -> None:
        md_status = market_data_service.status()
        if md_status.get("stale") and md_status.get("source") != "DEMO":
            self._strategy_status = "PAUSED_STALE_DATA"
            self._last_eval = utc_now().isoformat()
            return

        async with SessionLocal() as db:
            strat = await self._get_active_strategy(db)
            if not strat:
                self._strategy_status = "NO_ACTIVE_STRATEGY"
                self._last_eval = utc_now().isoformat()
                return

            self._strategy = SoreScalperPro(strat.parameters or {})
            portfolio = await self._get_portfolio(db)
            symbols = strat.symbols or ["CRUDEOIL"]
            timeframe = strat.timeframe or "5m"

            # Map symbol -> exchange from watchlist when available
            wl = (await db.execute(select(models.WatchlistItem))).scalars().all()
            exch_map = {w.symbol: w.exchange for w in wl}
            token_map = {w.symbol: w.token for w in wl if w.token}

            ltp_map = {}
            for symbol in symbols:
                exchange = exch_map.get(symbol, strat.exchange or "NSE")
                # Ensure candle series exists
                df = market_data_service.get_candles(symbol, timeframe, 250)
                if df is None or len(df) < 50:
                    continue
                tick = market_data_service.get_tick(symbol)
                if tick and tick.get("ltp"):
                    ltp_map[symbol] = float(tick["ltp"])
                # Attach token/exchange onto tick metadata for Angel path
                if symbol in token_map:
                    cur = market_data_service.get_tick(symbol) or {"symbol": symbol}
                    cur["token"] = token_map[symbol]
                    cur["exchange"] = exchange
                    market_data_service._ticks[symbol] = cur

                result = self._strategy.last_result(df.reset_index())
                self._last_eval = utc_now().isoformat()

                candle_ts = str(df.index[-1])
                key = f"{symbol}|{result.signal}|{candle_ts}|{strat.version}|{timeframe}"
                if result.signal in ("HOLD",) or key in self._last_candle_keys:
                    # Still update last signal display for non-HOLD on same bar once
                    if result.signal != "HOLD":
                        self._last_signal = {
                            "symbol": symbol,
                            "exchange": exchange,
                            "signal": result.signal,
                            "price": result.price,
                            "reason": result.reason,
                            "stop_loss": result.stop_loss,
                            "target": result.target,
                            "target2": result.target2,
                            "indicators": result.indicators,
                            "time": self._last_eval,
                        }
                    continue

                if result.signal == "HOLD":
                    continue

                self._last_candle_keys.add(key)
                idem = OrderManager.make_idempotency_key(
                    symbol, result.signal, candle_ts, strat.version, timeframe
                )

                # Persist signal
                existing = await db.execute(
                    select(models.Signal).where(models.Signal.idempotency_key == idem)
                )
                if existing.scalar_one_or_none():
                    continue

                qty = max(1, int(portfolio.max_position_size // max(result.price, 1)))
                # Crude oil futures: use lot-friendly qty default
                if symbol == "CRUDEOIL":
                    qty = max(1, min(qty, 1))
                sig = models.Signal(
                    idempotency_key=idem,
                    strategy_id=strat.id,
                    strategy_version=strat.version,
                    symbol=symbol,
                    exchange=exchange,
                    instrument_token=token_map.get(symbol, ""),
                    timeframe=timeframe,
                    signal_type=result.signal,
                    price=result.price,
                    stop_loss=result.stop_loss,
                    target=result.target,
                    target2=result.target2,
                    quantity=qty,
                    reason=result.reason,
                    indicator_values=result.indicators,
                    confidence=None,  # Pine does not provide confidence
                    candle_ts=utc_now(),
                )
                db.add(sig)
                await db.commit()
                await db.refresh(sig)

                self._last_signal = {
                    "id": sig.id,
                    "symbol": symbol,
                    "signal": result.signal,
                    "price": result.price,
                    "reason": result.reason,
                    "stop_loss": result.stop_loss,
                    "target": result.target,
                    "target2": result.target2,
                    "quantity": qty,
                    "indicators": result.indicators,
                    "time": self._last_eval,
                    "strategy": strat.name,
                    "version": strat.version,
                }

                market_valid = not md_status.get("stale") or md_status.get("source") == "DEMO"
                order_result = await self.order_manager.process_signal(
                    db,
                    portfolio=portfolio,
                    signal=sig,
                    strategy_active=bool(strat.is_active),
                    market_data_valid=market_valid,
                    data_source=md_status.get("source", "DEMO"),
                )

                note = {
                    "type": result.signal,
                    "title": f"NEW {result.signal} SIGNAL",
                    "symbol": symbol,
                    "price": result.price,
                    "strategy": strat.name,
                    "timeframe": timeframe,
                    "entry": result.price,
                    "sl": result.stop_loss,
                    "target": result.target,
                    "order": order_result,
                    "mode": "PAPER",
                    "ts": self._last_eval,
                }
                self._notifications.append(note)
                if len(self._notifications) > 100:
                    self._notifications = self._notifications[-100:]

                db.add(
                    models.AuditLog(
                        category="SIGNAL",
                        action=f"SIGNAL_{result.signal}",
                        symbol=symbol,
                        strategy=strat.name,
                        signal=result.signal,
                        detail={"reason": result.reason, "order": order_result},
                    )
                )
                await db.commit()

            if ltp_map:
                await refresh_portfolio_marks(db, portfolio, ltp_map)

            # Auto-complete 7-day experiment if due
            await self._maybe_complete_experiment(db)

    async def _get_active_strategy(self, db: AsyncSession) -> models.StrategyConfig | None:
        result = await db.execute(
            select(models.StrategyConfig).where(models.StrategyConfig.is_active == True)  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def _get_portfolio(self, db: AsyncSession) -> models.Portfolio:
        result = await db.execute(select(models.Portfolio).limit(1))
        port = result.scalar_one_or_none()
        if not port:
            from app.core.config import get_settings

            s = get_settings()
            port = models.Portfolio(
                name="Paper Portfolio",
                mode="PAPER",
                starting_capital=s.default_starting_capital,
                cash=s.default_starting_capital,
                equity=s.default_starting_capital,
                peak_equity=s.default_starting_capital,
            )
            db.add(port)
            await db.commit()
            await db.refresh(port)
        return port

    async def _maybe_complete_experiment(self, db: AsyncSession) -> None:
        result = await db.execute(
            select(models.PaperExperiment).where(models.PaperExperiment.status == "RUNNING")
        )
        exp = result.scalar_one_or_none()
        if not exp:
            return
        ends = ensure_utc(exp.ends_at)
        if ends is None or utc_now() < ends:
            return
        from app.services.analytics.report import generate_experiment_report

        report = await generate_experiment_report(db, exp)
        exp.status = "COMPLETED"
        exp.completed_at = utc_now()
        exp.report = report
        exp.ending_capital = report.get("ending_capital")
        await db.commit()


signal_engine = SignalEngine()
