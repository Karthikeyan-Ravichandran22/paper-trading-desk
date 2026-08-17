"""FastAPI route modules."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.safety import current_mode_label, live_orders_allowed
from app.core.timeutil import format_ist, utc_now, ensure_utc
from app.db import models
from app.db.session import get_db
from app.services.analytics.backtest import run_backtest
from app.services.analytics.metrics import compute_metrics, refresh_portfolio_marks
from app.services.analytics.report import generate_experiment_report
from app.services.broker.angel_one import angel_client
from app.services.broker.live_broker import LiveBroker
from app.services.market.data_service import market_data_service
from app.services.market.session import market_status
from app.services.strategy.engine import signal_engine
from app.services.strategy.sore_scalper import DEFAULT_PARAMS, SoreScalperPro

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────
class AngelLoginRequest(BaseModel):
    totp: str = ""


class StrategyUpdate(BaseModel):
    name: Optional[str] = None
    pine_source: Optional[str] = None
    parameters: Optional[dict] = None
    symbols: Optional[list[str]] = None
    exchange: Optional[str] = None
    timeframe: Optional[str] = None
    activate: Optional[bool] = None


class PortfolioSettingsUpdate(BaseModel):
    starting_capital: Optional[float] = None
    max_position_size: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_open_positions: Optional[int] = None
    slippage_bps: Optional[float] = None
    brokerage_per_order: Optional[float] = None


class WatchlistAdd(BaseModel):
    symbol: str
    exchange: str = "NSE"
    token: str = ""


class BacktestRequest(BaseModel):
    symbol: str = "NIFTY"
    timeframe: str = "5m"
    starting_capital: float = 100_000
    bars: int = 300
    quantity: int = 50


class LiveModeRequest(BaseModel):
    enable: bool
    confirmation: str = ""


# ── Status ───────────────────────────────────────────────────────────
@router.get("/status")
async def system_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    settings = get_settings()
    md = market_data_service.status()
    se = signal_engine.status()
    strat = (
        await db.execute(
            select(models.StrategyConfig).where(models.StrategyConfig.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    return {
        "app": settings.app_name,
        "trading_mode": current_mode_label(),
        "paper_trading_banner": "PAPER TRADING",
        "live_trading": "DISABLED" if not live_orders_allowed() else "ENABLED",
        "live_trading_enabled_flag": settings.live_trading_enabled,
        "angel_one": {
            **angel_client.status(),
            "label": "CONNECTED" if angel_client.is_connected else (
                "CONFIGURED" if angel_client.is_configured else "NOT_CONFIGURED"
            ),
        },
        "market_data": md,
        "market_status": market_status(),
        "websocket": md.get("websocket"),
        "strategy": {
            "name": strat.name if strat else None,
            "version": strat.version if strat else None,
            "status": se.get("strategy"),
            "timeframe": strat.timeframe if strat else None,
        },
        "paper_engine": "ACTIVE",
        "last_tick": md.get("last_tick"),
        "last_strategy_evaluation": se.get("last_evaluation"),
        "data_source_note": (
            "DEMO market data active — prices are synthetic for paper testing. "
            "Connect Angel One for live market data."
            if md.get("source") == "DEMO"
            else "Live market data from Angel One."
        ),
    }


@router.get("/mode")
async def get_mode() -> dict:
    return {
        "mode": current_mode_label(),
        "live_orders_allowed": live_orders_allowed(),
        "banner": "PAPER MODE",
        "can_enable_live": False,
        "reason": "LIVE MODE remains disabled for the first implementation / 7-day paper test.",
    }


@router.post("/mode/live")
async def attempt_live_mode(body: LiveModeRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Explicitly reject enabling live mode during paper phase."""
    db.add(
        models.AuditLog(
            category="SAFETY",
            action="LIVE_MODE_ACTIVATION_BLOCKED",
            detail={"requested_enable": body.enable, "confirmation": bool(body.confirmation)},
            level="WARN",
        )
    )
    await db.commit()
    raise HTTPException(
        status_code=403,
        detail=(
            "LIVE MODE is disabled for this build. Complete the 7-day paper-trading "
            "experiment and manual human review before live trading can be considered. "
            "No Angel One order API was called."
        ),
    )


# ── Angel One ────────────────────────────────────────────────────────
@router.post("/angel/login")
async def angel_login(body: AngelLoginRequest) -> dict:
    result = await angel_client.login(totp=body.totp)
    return result


@router.get("/angel/status")
async def angel_status() -> dict:
    return angel_client.status()


# ── Watchlist / Quotes ───────────────────────────────────────────────
@router.get("/watchlist")
async def get_watchlist(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.execute(select(models.WatchlistItem).order_by(models.WatchlistItem.sort_order))
    ).scalars().all()
    symbols = [r.symbol for r in rows]
    quotes = market_data_service.get_watchlist_quotes(symbols)

    # Attach signal/position
    last_sig = signal_engine.status().get("last_signal")
    positions = (
        await db.execute(select(models.Position).where(models.Position.status == "OPEN"))
    ).scalars().all()
    pos_map = {p.symbol: p.side for p in positions}
    meta = {r.symbol: r for r in rows}

    out = []
    for q in quotes:
        sig = None
        if last_sig and last_sig.get("symbol") == q["symbol"]:
            sig = last_sig.get("signal")
        item = meta.get(q["symbol"])
        out.append(
            {
                **q,
                "exchange": (item.exchange if item else q.get("exchange")) or "NSE",
                "token": (item.token if item else "") or q.get("token") or "",
                "signal": sig,
                "position": pos_map.get(q["symbol"]),
            }
        )
    return out


@router.post("/watchlist")
async def add_watchlist(body: WatchlistAdd, db: AsyncSession = Depends(get_db)) -> dict:
    from app.services.market.instruments import resolve_instrument

    resolved = await resolve_instrument(body.symbol, body.exchange)
    symbol = resolved["symbol"]
    exchange = resolved["exchange"]
    token = body.token or resolved.get("token") or ""

    existing = (
        await db.execute(
            select(models.WatchlistItem).where(
                models.WatchlistItem.symbol == symbol,
                models.WatchlistItem.exchange == exchange,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if token and not existing.token:
            existing.token = token
            await db.commit()
        return {
            "status": "exists",
            "symbol": existing.symbol,
            "exchange": existing.exchange,
            "token": existing.token,
            "trading_symbol": resolved.get("trading_symbol"),
            "expiry": resolved.get("expiry"),
        }
    item = models.WatchlistItem(symbol=symbol, exchange=exchange, token=token)
    db.add(item)
    await db.commit()
    market_data_service.get_candles(symbol, "5m", 200)
    # Prefer Angel LTP when token is known
    tick = market_data_service.get_tick(symbol) or {}
    tick.update(
        {
            "symbol": symbol,
            "exchange": exchange,
            "token": token,
            "trading_symbol": resolved.get("trading_symbol"),
            "source": market_data_service.source,
        }
    )
    market_data_service._ticks[symbol] = tick
    return {
        "status": "added",
        "symbol": item.symbol,
        "exchange": item.exchange,
        "token": item.token,
        "trading_symbol": resolved.get("trading_symbol"),
        "expiry": resolved.get("expiry"),
        "lot_size": resolved.get("lot_size"),
    }


@router.delete("/watchlist/{symbol}")
async def remove_watchlist(symbol: str, db: AsyncSession = Depends(get_db)) -> dict:
    row = (
        await db.execute(
            select(models.WatchlistItem).where(models.WatchlistItem.symbol == symbol.upper())
        )
    ).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return {"status": "removed", "symbol": symbol.upper()}


# ── Candles / Chart ──────────────────────────────────────────────────
@router.get("/candles/{symbol}")
async def get_candles(symbol: str, timeframe: str = "5m", limit: int = 200) -> dict:
    df = market_data_service.get_candles(symbol.upper(), timeframe, limit)
    candles = []
    for ts, row in df.iterrows():
        candles.append(
            {
                "time": int(ts.timestamp()) if hasattr(ts, "timestamp") else ts,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
        )
    # Strategy overlays for last run
    strategy = SoreScalperPro()
    computed = strategy.compute_dataframe(df.reset_index())
    markers = []
    levels = {}
    for i, row in computed.iterrows():
        if row["signal"] in ("BUY", "SELL", "EXIT"):
            ts = df.index[i] if i < len(df.index) else None
            t = int(ts.timestamp()) if ts is not None and hasattr(ts, "timestamp") else None
            if t:
                markers.append(
                    {
                        "time": t,
                        "position": "belowBar" if row["signal"] == "BUY" else "aboveBar",
                        "color": "#00E676" if row["signal"] == "BUY" else (
                            "#FF1744" if row["signal"] == "SELL" else "#E040FB"
                        ),
                        "shape": "arrowUp" if row["signal"] == "BUY" else (
                            "arrowDown" if row["signal"] == "SELL" else "circle"
                        ),
                        "text": row["signal"],
                    }
                )
    last = computed.iloc[-1] if len(computed) else None
    if last is not None and last.get("ep") is not None:
        levels = {
            "ep": last.get("ep"),
            "sl": last.get("sl"),
            "tp1": last.get("tp1"),
            "tp2": last.get("tp2"),
            "ema_fast": float(last["ema_fast"]) if last.get("ema_fast") == last.get("ema_fast") else None,
            "ema_slow": float(last["ema_slow"]) if last.get("ema_slow") == last.get("ema_slow") else None,
            "st_line": float(last["st_line"]) if last.get("st_line") == last.get("st_line") else None,
        }
    return {
        "symbol": symbol.upper(),
        "exchange": "NSE",
        "timeframe": timeframe,
        "source": market_data_service.source,
        "candles": candles,
        "markers": markers,
        "levels": levels,
        "timezone": "Asia/Kolkata",
    }


# ── Signals ──────────────────────────────────────────────────────────
@router.get("/signals")
async def list_signals(limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.execute(select(models.Signal).order_by(desc(models.Signal.created_at)).limit(limit))
    ).scalars().all()
    return [
        {
            "id": s.id,
            "symbol": s.symbol,
            "signal": s.signal_type,
            "price": s.price,
            "stop_loss": s.stop_loss,
            "target": s.target,
            "target2": s.target2,
            "quantity": s.quantity,
            "reason": s.reason,
            "indicators": s.indicator_values,
            "strategy_version": s.strategy_version,
            "acted_on": s.acted_on,
            "rejection_reason": s.rejection_reason,
            "time": format_ist(s.created_at),
            "confidence": s.confidence,
        }
        for s in rows
    ]


@router.get("/signals/current")
async def current_signal() -> dict:
    return signal_engine.status().get("last_signal") or {
        "signal": "HOLD",
        "reason": "Waiting for strategy conditions",
    }


@router.get("/notifications")
async def notifications() -> list[dict]:
    return signal_engine.pop_notifications()[-20:]


# ── Portfolio / Positions / Trades ───────────────────────────────────
@router.get("/portfolio")
async def get_portfolio(db: AsyncSession = Depends(get_db)) -> dict:
    port = (await db.execute(select(models.Portfolio).limit(1))).scalar_one_or_none()
    if not port:
        raise HTTPException(404, "Portfolio not found")
    # Refresh marks
    wl = (await db.execute(select(models.WatchlistItem))).scalars().all()
    ltp_map = {}
    for w in wl:
        t = market_data_service.get_ltp(w.symbol)
        if t:
            ltp_map[w.symbol] = t
    await refresh_portfolio_marks(db, port, ltp_map)
    await db.refresh(port)
    metrics = await compute_metrics(db, port.id)
    positions = (
        await db.execute(
            select(models.Position).where(
                models.Position.portfolio_id == port.id,
                models.Position.status == "OPEN",
            )
        )
    ).scalars().all()
    invested = sum(p.entry_price * p.quantity for p in positions)
    ret = ((port.equity - port.starting_capital) / port.starting_capital * 100) if port.starting_capital else 0
    return {
        "mode": "PAPER",
        "name": port.name,
        "initial_capital": port.starting_capital,
        "current_equity": port.equity,
        "available_cash": port.cash,
        "invested_capital": round(invested, 2),
        "realized_pnl": port.realized_pnl,
        "unrealized_pnl": port.unrealized_pnl,
        "total_pnl": round(port.realized_pnl + port.unrealized_pnl, 2),
        "return_pct": round(ret, 4),
        "maximum_drawdown": port.max_drawdown,
        "cost_assumptions": {
            "slippage_bps": port.slippage_bps,
            "brokerage_per_order": port.brokerage_per_order,
            "stt_rate": port.stt_rate,
            "exchange_rate": port.exchange_rate,
            "gst_rate": port.gst_rate,
            "sebi_rate": port.sebi_rate,
            "stamp_duty_rate": port.stamp_duty_rate,
            "disclaimer": "Simulated P&L is not identical to actual broker P&L.",
        },
        "metrics": metrics,
        "settings": {
            "max_position_size": port.max_position_size,
            "max_daily_loss": port.max_daily_loss,
            "max_open_positions": port.max_open_positions,
        },
    }


@router.patch("/portfolio/settings")
async def update_portfolio_settings(
    body: PortfolioSettingsUpdate, db: AsyncSession = Depends(get_db)
) -> dict:
    port = (await db.execute(select(models.Portfolio).limit(1))).scalar_one_or_none()
    if not port:
        raise HTTPException(404, "Portfolio not found")
    data = body.model_dump(exclude_none=True)
    if "starting_capital" in data:
        # Only allow reset-style change when no trades
        trades = (
            await db.execute(select(models.Trade).where(models.Trade.portfolio_id == port.id))
        ).scalars().first()
        if trades:
            raise HTTPException(400, "Cannot change starting capital after trades exist")
        port.starting_capital = data.pop("starting_capital")
        port.cash = port.starting_capital
        port.equity = port.starting_capital
        port.peak_equity = port.starting_capital
    for k, v in data.items():
        setattr(port, k, v)
    await db.commit()
    return {"status": "updated"}


@router.get("/positions")
async def get_positions(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.execute(select(models.Position).where(models.Position.status == "OPEN"))
    ).scalars().all()
    return [
        {
            "id": p.id,
            "symbol": p.symbol,
            "side": p.side,
            "quantity": p.quantity,
            "entry": p.entry_price,
            "ltp": p.current_price,
            "unrealized_pnl": p.unrealized_pnl,
            "stop_loss": p.stop_loss,
            "target": p.target,
            "target2": p.target2,
            "strategy_version": p.strategy_version,
            "entry_reason": p.entry_reason,
            "opened_at": format_ist(p.opened_at),
        }
        for p in rows
    ]


@router.get("/orders")
async def get_orders(limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.execute(
            select(models.PaperOrder).order_by(desc(models.PaperOrder.created_at)).limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": o.id,
            "symbol": o.symbol,
            "side": o.side,
            "qty": o.quantity,
            "requested": o.requested_price,
            "fill": o.fill_price,
            "status": o.status,
            "broker": o.broker_used,
            "brokerage": o.brokerage,
            "charges": o.charges,
            "slippage": o.slippage,
            "rejection_reason": o.rejection_reason,
            "strategy_version": o.strategy_version,
            "time": format_ist(o.created_at),
            "mode": "PAPER",
        }
        for o in rows
    ]


@router.get("/trades")
async def get_trades(limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.execute(
            select(models.Trade)
            .where(models.Trade.is_backtest == False)  # noqa: E712
            .order_by(desc(models.Trade.closed_at))
            .limit(limit)
        )
    ).scalars().all()
    return [
        {
            "id": t.id,
            "time": format_ist(t.closed_at),
            "symbol": t.symbol,
            "side": t.side,
            "entry": t.entry_price,
            "exit": t.exit_price,
            "qty": t.quantity,
            "pnl": t.net_pnl,
            "pnl_pct": t.pnl_pct,
            "duration_seconds": t.duration_seconds,
            "reason": t.exit_reason,
            "expanded": {
                "entry_reason": t.entry_reason,
                "exit_reason": t.exit_reason,
                "indicators": t.indicator_values,
                "strategy_version": t.strategy_version,
                "stop_loss": t.stop_loss,
                "target": t.target,
                "slippage": t.slippage,
                "brokerage": t.brokerage,
                "charges": t.charges,
                "gross_pnl": t.gross_pnl,
                "net_pnl": t.net_pnl,
                "opened_at": format_ist(t.opened_at),
                "closed_at": format_ist(t.closed_at),
            },
        }
        for t in rows
    ]


# ── Performance ──────────────────────────────────────────────────────
@router.get("/performance")
async def performance(db: AsyncSession = Depends(get_db)) -> dict:
    port = (await db.execute(select(models.Portfolio).limit(1))).scalar_one_or_none()
    if not port:
        raise HTTPException(404, "Portfolio not found")
    metrics = await compute_metrics(db, port.id)
    snaps = (
        await db.execute(
            select(models.EquitySnapshot)
            .where(models.EquitySnapshot.portfolio_id == port.id)
            .order_by(models.EquitySnapshot.created_at)
            .limit(500)
        )
    ).scalars().all()
    trades = (
        await db.execute(
            select(models.Trade).where(models.Trade.is_backtest == False)  # noqa: E712
        )
    ).scalars().all()
    daily: dict[str, float] = {}
    for t in trades:
        day = format_ist(t.closed_at)
        if day:
            d = day[:10]
            daily[d] = daily.get(d, 0) + t.net_pnl
    return {
        "label": "LIVE MARKET / PAPER TRADE",
        "metrics": metrics,
        "equity_curve": [
            {"ts": format_ist(s.created_at), "equity": s.equity} for s in snaps
        ],
        "daily_pnl": [{"date": k, "pnl": round(v, 2)} for k, v in sorted(daily.items())],
        "distribution": {
            "winning": metrics["winning_trades"],
            "losing": metrics["losing_trades"],
            "breakeven": metrics["breakeven_trades"],
        },
    }


# ── Strategy ─────────────────────────────────────────────────────────
@router.get("/strategy")
async def get_strategy(db: AsyncSession = Depends(get_db)) -> dict:
    strat = (await db.execute(select(models.StrategyConfig).limit(1))).scalar_one_or_none()
    if not strat:
        raise HTTPException(404, "No strategy")
    return {
        "id": strat.id,
        "name": strat.name,
        "version": strat.version,
        "pine_source": strat.pine_source,
        "parameters": strat.parameters,
        "symbols": strat.symbols,
        "exchange": strat.exchange,
        "timeframe": strat.timeframe,
        "is_active": strat.is_active,
        "validation_status": strat.validation_status,
        "validation_report": strat.validation_report,
        "unsupported_features": strat.unsupported_features,
    }


@router.post("/strategy/validate")
async def validate_strategy(body: StrategyUpdate) -> dict:
    pine = body.pine_source or ""
    params = body.parameters or DEFAULT_PARAMS
    report = SoreScalperPro.validate(pine, params)
    return {
        "title": "STRATEGY VALIDATION",
        "passed": report.passed,
        "checks": report.checks,
        "unsupported": report.unsupported,
        "warnings": report.warnings,
        "message": (
            "Strategy validation passed."
            if report.passed
            else "STRATEGY VALIDATION FAILED — strategy has NOT been activated."
        ),
    }


@router.put("/strategy")
async def update_strategy(body: StrategyUpdate, db: AsyncSession = Depends(get_db)) -> dict:
    strat = (await db.execute(select(models.StrategyConfig).limit(1))).scalar_one_or_none()
    if not strat:
        raise HTTPException(404, "No strategy")
    pine = body.pine_source if body.pine_source is not None else strat.pine_source
    params = body.parameters if body.parameters is not None else strat.parameters
    report = SoreScalperPro.validate(pine, params)
    if body.activate and not report.passed:
        raise HTTPException(
            400,
            detail={
                "message": "STRATEGY VALIDATION FAILED — strategy has NOT been activated.",
                "unsupported": report.unsupported,
                "checks": report.checks,
            },
        )
    if body.name is not None:
        strat.name = body.name
    if body.pine_source is not None:
        strat.pine_source = body.pine_source
    if body.parameters is not None:
        strat.parameters = body.parameters
    if body.symbols is not None:
        strat.symbols = body.symbols
    if body.exchange is not None:
        strat.exchange = body.exchange
    if body.timeframe is not None:
        strat.timeframe = body.timeframe
    strat.validation_status = "PASS" if report.passed else "FAIL"
    strat.validation_report = {"checks": report.checks, "warnings": report.warnings}
    strat.unsupported_features = report.unsupported
    if body.activate is not None:
        strat.is_active = body.activate and report.passed
    # Bump version on param/pine change
    parts = strat.version.split(".")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
        strat.version = ".".join(parts)
    except Exception:
        strat.version = strat.version + ".1"
    await db.commit()
    return {"status": "updated", "version": strat.version, "is_active": strat.is_active, "validation": report.checks}


# ── Experiment ───────────────────────────────────────────────────────
@router.get("/experiment")
async def get_experiment(db: AsyncSession = Depends(get_db)) -> dict:
    exp = (
        await db.execute(
            select(models.PaperExperiment).order_by(desc(models.PaperExperiment.id)).limit(1)
        )
    ).scalar_one_or_none()
    if not exp:
        return {"status": "NONE"}
    payload = {
        "id": exp.id,
        "name": exp.name,
        "status": exp.status,
        "strategy": exp.strategy_name,
        "symbols": exp.symbols,
        "timeframe": exp.timeframe,
        "starting_capital": exp.starting_capital,
        "ending_capital": exp.ending_capital,
        "started_at": format_ist(exp.started_at),
        "ends_at": format_ist(exp.ends_at),
        "completed_at": format_ist(exp.completed_at),
        "report": exp.report if exp.status == "COMPLETED" else None,
    }
    if exp.status == "RUNNING" and exp.ends_at:
        remaining = ensure_utc(exp.ends_at) - utc_now()
        payload["remaining_seconds"] = max(0, int(remaining.total_seconds()))
    return payload


@router.post("/experiment/start")
async def start_experiment(db: AsyncSession = Depends(get_db)) -> dict:
    running = (
        await db.execute(
            select(models.PaperExperiment).where(models.PaperExperiment.status == "RUNNING")
        )
    ).scalar_one_or_none()
    if running:
        raise HTTPException(400, "A paper test is already running")
    settings = get_settings()
    strat = (await db.execute(select(models.StrategyConfig).limit(1))).scalar_one()
    now = utc_now()
    exp = models.PaperExperiment(
        name="7-DAY PAPER TEST",
        strategy_id=strat.id,
        strategy_name=strat.name,
        symbols=strat.symbols,
        timeframe=strat.timeframe,
        starting_capital=settings.default_starting_capital,
        status="RUNNING",
        started_at=now,
        ends_at=now + timedelta(days=7),
    )
    db.add(exp)
    await db.commit()
    return {"status": "started", "ends_at": format_ist(exp.ends_at)}


@router.post("/experiment/report")
async def force_report(db: AsyncSession = Depends(get_db)) -> dict:
    """Generate current snapshot report without waiting for day 7 (for review)."""
    exp = (
        await db.execute(
            select(models.PaperExperiment).order_by(desc(models.PaperExperiment.id)).limit(1)
        )
    ).scalar_one_or_none()
    if not exp:
        raise HTTPException(404, "No experiment")
    report = await generate_experiment_report(db, exp)
    return report


# ── Backtest ─────────────────────────────────────────────────────────
@router.post("/backtest")
async def backtest(body: BacktestRequest) -> dict:
    df = market_data_service.get_candles(body.symbol.upper(), body.timeframe, body.bars)
    result = await run_backtest(
        df.reset_index(),
        symbol=body.symbol.upper(),
        timeframe=body.timeframe,
        starting_capital=body.starting_capital,
        qty=body.quantity,
    )
    return result


# ── Audit / Logs ─────────────────────────────────────────────────────
@router.get("/audit")
async def audit_logs(limit: int = 200, db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.execute(select(models.AuditLog).order_by(desc(models.AuditLog.timestamp)).limit(limit))
    ).scalars().all()
    return [
        {
            "id": a.id,
            "timestamp": format_ist(a.timestamp),
            "user": a.user,
            "category": a.category,
            "action": a.action,
            "symbol": a.symbol,
            "strategy": a.strategy,
            "signal": a.signal,
            "order_id": a.order_id,
            "detail": a.detail,
            "level": a.level,
        }
        for a in rows
    ]


# ── Safety probe (for tests / UI) ────────────────────────────────────
@router.post("/safety/probe-live-order")
async def probe_live_order() -> dict:
    """Prove live order path is blocked."""
    broker = LiveBroker()
    try:
        await broker.place_order_via_angel({"symbol": "NIFTY"})
        return {"blocked": False, "error": "UNEXPECTED — live path was not blocked"}
    except Exception as exc:
        return {
            "blocked": True,
            "mode": "PAPER",
            "message": str(exc),
            "angel_order_api_called": False,
        }
