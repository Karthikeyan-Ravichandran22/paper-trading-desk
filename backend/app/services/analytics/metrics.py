"""Portfolio & analytics helpers."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import utc_now
from app.db import models


async def refresh_portfolio_marks(
    db: AsyncSession,
    portfolio: models.Portfolio,
    ltp_map: dict[str, float],
) -> models.Portfolio:
    result = await db.execute(
        select(models.Position).where(
            models.Position.portfolio_id == portfolio.id,
            models.Position.status == "OPEN",
        )
    )
    positions = list(result.scalars().all())
    unrealized = 0.0
    invested = 0.0
    for pos in positions:
        ltp = ltp_map.get(pos.symbol, pos.current_price or pos.entry_price)
        pos.current_price = ltp
        if pos.side == "LONG":
            upnl = (ltp - pos.entry_price) * pos.quantity
        else:
            upnl = (pos.entry_price - ltp) * pos.quantity
        pos.unrealized_pnl = round(upnl, 2)
        unrealized += upnl
        invested += pos.entry_price * pos.quantity

    portfolio.unrealized_pnl = round(unrealized, 2)
    portfolio.equity = round(portfolio.cash + invested + unrealized - invested + invested, 2)
    # equity = cash + MTM value of positions
    mtm_value = 0.0
    for pos in positions:
        mtm_value += pos.current_price * pos.quantity
    # For shorts, cash already includes proceeds; equity ≈ cash - short liability + long value
    long_value = sum(p.current_price * p.quantity for p in positions if p.side == "LONG")
    short_liability = sum(p.current_price * p.quantity for p in positions if p.side == "SHORT")
    # Simpler consistent definition:
    portfolio.equity = round(portfolio.starting_capital + portfolio.realized_pnl + unrealized, 2)
    if portfolio.equity > portfolio.peak_equity:
        portfolio.peak_equity = portfolio.equity
    dd = 0.0
    if portfolio.peak_equity > 0:
        dd = (portfolio.peak_equity - portfolio.equity) / portfolio.peak_equity * 100
    portfolio.max_drawdown = max(portfolio.max_drawdown, round(dd, 4))
    portfolio.updated_at = utc_now()

    db.add(
        models.EquitySnapshot(
            portfolio_id=portfolio.id,
            equity=portfolio.equity,
            cash=portfolio.cash,
            unrealized_pnl=portfolio.unrealized_pnl,
            realized_pnl=portfolio.realized_pnl,
        )
    )
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


async def compute_metrics(db: AsyncSession, portfolio_id: int) -> dict[str, Any]:
    result = await db.execute(
        select(models.Trade).where(
            models.Trade.portfolio_id == portfolio_id,
            models.Trade.is_backtest == False,  # noqa: E712
        )
    )
    trades = list(result.scalars().all())
    closed = trades
    wins = [t for t in closed if t.net_pnl > 0]
    losses = [t for t in closed if t.net_pnl < 0]
    breakeven = [t for t in closed if t.net_pnl == 0]
    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    net = sum(t.net_pnl for t in closed)
    win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    avg_trade = net / len(closed) if closed else 0.0
    avg_win = (sum(t.net_pnl for t in wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(t.net_pnl for t in losses) / len(losses)) if losses else 0.0
    largest_win = max((t.net_pnl for t in wins), default=0.0)
    largest_loss = min((t.net_pnl for t in losses), default=0.0)

    # Consecutive
    max_cons_wins = max_cons_losses = cur_w = cur_l = 0
    for t in sorted(closed, key=lambda x: x.closed_at or utc_now()):
        if t.net_pnl > 0:
            cur_w += 1
            cur_l = 0
            max_cons_wins = max(max_cons_wins, cur_w)
        elif t.net_pnl < 0:
            cur_l += 1
            cur_w = 0
            max_cons_losses = max(max_cons_losses, cur_l)
        else:
            cur_w = cur_l = 0

    port = await db.get(models.Portfolio, portfolio_id)
    return {
        "total_trades": len(closed),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "breakeven_trades": len(breakeven),
        "win_rate": round(win_rate, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_profit": round(net, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else None,
        "profit_factor_infinite": profit_factor == float("inf"),
        "average_trade": round(avg_trade, 2),
        "average_win": round(avg_win, 2),
        "average_loss": round(avg_loss, 2),
        "largest_win": round(largest_win, 2),
        "largest_loss": round(largest_loss, 2),
        "maximum_drawdown_pct": port.max_drawdown if port else 0,
        "max_consecutive_wins": max_cons_wins,
        "max_consecutive_losses": max_cons_losses,
        "note": "Metrics exclude open/unrealized trades unless labelled separately.",
    }
