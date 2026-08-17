"""Simple backtester — clearly labelled BACKTEST, never mixed with paper account."""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.strategy.sore_scalper import SoreScalperPro
from app.services.broker.paper_broker import PaperBroker


async def run_backtest(
    df: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    starting_capital: float = 100_000.0,
    params: dict | None = None,
    qty: int = 50,
) -> dict[str, Any]:
    strategy = SoreScalperPro(params)
    computed = strategy.compute_dataframe(df.reset_index(drop=True) if "close" in df.columns else df)
    broker = PaperBroker()

    cash = starting_capital
    position = None
    trades = []
    equity_curve = []

    for i, row in computed.iterrows():
        price = float(row["close"])
        sig = row["signal"]
        equity = cash
        if position:
            if position["side"] == "LONG":
                equity = cash + price * position["qty"]
            else:
                equity = cash - price * position["qty"] + position["entry"] * position["qty"]
        equity_curve.append({"i": int(i) if not isinstance(i, int) else i, "equity": round(equity, 2)})

        if sig == "BUY" and position is None:
            fill = price * (1 + 0.0005)
            cost = fill * qty + 20
            if cost > cash:
                continue
            cash -= cost
            position = {
                "side": "LONG",
                "qty": qty,
                "entry": fill,
                "sl": row["sl"],
                "tp": row["tp1"],
                "reason": row["reason"],
            }
        elif sig == "SELL" and position is None:
            fill = price * (1 - 0.0005)
            cash += fill * qty - 20
            position = {
                "side": "SHORT",
                "qty": qty,
                "entry": fill,
                "sl": row["sl"],
                "tp": row["tp1"],
                "reason": row["reason"],
            }
        elif sig == "EXIT" and position is not None:
            if position["side"] == "LONG":
                fill = price * (1 - 0.0005)
                gross = (fill - position["entry"]) * qty
                cash += fill * qty - 20
            else:
                fill = price * (1 + 0.0005)
                gross = (position["entry"] - fill) * qty
                cash -= fill * qty + 20
            trades.append(
                {
                    "side": position["side"],
                    "entry": position["entry"],
                    "exit": fill,
                    "qty": qty,
                    "gross_pnl": round(gross, 2),
                    "net_pnl": round(gross - 40, 2),
                    "entry_reason": position["reason"],
                    "exit_reason": row["reason"],
                }
            )
            position = None

    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] < 0]
    net = sum(t["net_pnl"] for t in trades)
    gross_profit = sum(t["net_pnl"] for t in wins)
    gross_loss = abs(sum(t["net_pnl"] for t in losses))
    peak = starting_capital
    max_dd = 0.0
    for pt in equity_curve:
        peak = max(peak, pt["equity"])
        dd = (peak - pt["equity"]) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    return {
        "label": "BACKTEST",
        "not_paper_trading": True,
        "symbol": symbol,
        "timeframe": timeframe,
        "starting_capital": starting_capital,
        "ending_capital": round(equity_curve[-1]["equity"] if equity_curve else starting_capital, 2),
        "total_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0,
        "net_pnl": round(net, 2),
        "maximum_drawdown_pct": round(max_dd, 4),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "equity_curve": equity_curve[:: max(1, len(equity_curve) // 200)],
        "trades": trades,
        "disclaimer": "BACKTEST results are historical simulation only and are NOT mixed with the live paper-trading account.",
    }
