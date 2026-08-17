"""Order manager — routes signals through risk → broker abstraction (Paper only)."""
from __future__ import annotations

import hashlib
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.safety import current_mode_label
from app.core.timeutil import utc_now, ensure_utc
from app.db import models
from app.services.broker.base import BrokerOrderRequest, OrderSide
from app.services.broker.factory import assert_no_live_orders_in_paper, get_broker
from app.services.risk.engine import RiskEngine


class OrderManager:
    def __init__(self, risk: RiskEngine | None = None):
        self.risk = risk or RiskEngine()

    @staticmethod
    def make_idempotency_key(
        symbol: str,
        signal_type: str,
        candle_ts: str,
        strategy_version: str,
        timeframe: str,
    ) -> str:
        raw = f"{symbol}|{signal_type}|{candle_ts}|{strategy_version}|{timeframe}"
        return hashlib.sha256(raw.encode()).hexdigest()[:48]

    async def process_signal(
        self,
        db: AsyncSession,
        *,
        portfolio: models.Portfolio,
        signal: models.Signal,
        strategy_active: bool,
        market_data_valid: bool,
        data_source: str = "DEMO",
    ) -> dict[str, Any]:
        mode = current_mode_label()
        assert mode == "PAPER" or not __import__("app.core.config", fromlist=["get_settings"]).get_settings().live_trading_enabled

        # Existing open position?
        pos_result = await db.execute(
            select(models.Position).where(
                models.Position.portfolio_id == portfolio.id,
                models.Position.symbol == signal.symbol,
                models.Position.status == "OPEN",
            )
        )
        open_pos = pos_result.scalar_one_or_none()
        open_count_result = await db.execute(
            select(models.Position).where(
                models.Position.portfolio_id == portfolio.id,
                models.Position.status == "OPEN",
            )
        )
        open_positions = list(open_count_result.scalars().all())

        qty = signal.quantity or max(1, int(portfolio.max_position_size // max(signal.price, 1)))

        # EXIT handling
        if signal.signal_type == "EXIT":
            if not open_pos:
                signal.rejection_reason = "No open position to exit"
                await db.commit()
                return {"status": "IGNORED", "reason": signal.rejection_reason}
            return await self._close_position(
                db, portfolio, open_pos, signal, reason=signal.reason or "Exit signal"
            )

        decision = self.risk.validate(
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            price=signal.price,
            quantity=qty,
            idempotency_key=signal.idempotency_key,
            strategy_active=strategy_active,
            open_positions=len(open_positions),
            has_open_position_for_symbol=open_pos is not None,
            available_cash=portfolio.cash,
            market_data_valid=market_data_valid,
            data_source=data_source,
        )

        if not decision.allowed:
            signal.rejection_reason = decision.reason
            await self._audit(
                db,
                category="RISK",
                action="ORDER_REJECTED",
                symbol=signal.symbol,
                signal=signal.signal_type,
                detail={"reason": decision.reason},
            )
            await db.commit()
            return {"status": "REJECTED", "reason": decision.reason}

        # Duplicate order check at DB level
        existing = await db.execute(
            select(models.PaperOrder).where(
                models.PaperOrder.idempotency_key == signal.idempotency_key
            )
        )
        if existing.scalar_one_or_none():
            signal.rejection_reason = "Duplicate signal ignored"
            await db.commit()
            return {"status": "REJECTED", "reason": "Duplicate signal ignored"}

        broker = get_broker(
            slippage_bps=portfolio.slippage_bps,
            brokerage_per_order=portfolio.brokerage_per_order,
            stt_rate=portfolio.stt_rate,
            exchange_rate=portfolio.exchange_rate,
            gst_rate=portfolio.gst_rate,
            sebi_rate=portfolio.sebi_rate,
            stamp_duty_rate=portfolio.stamp_duty_rate,
        )
        assert_no_live_orders_in_paper(broker)
        if broker.is_live:
            raise RuntimeError("Safety violation: refused to use live broker in paper flow")

        side = OrderSide.BUY if signal.signal_type == "BUY" else OrderSide.SELL
        # For short entries we still "SELL" to open short in paper engine
        req = BrokerOrderRequest(
            symbol=signal.symbol,
            exchange=signal.exchange,
            side=side,
            quantity=qty,
            price=signal.price,
            stop_loss=signal.stop_loss,
            target=signal.target,
            target2=signal.target2,
            idempotency_key=signal.idempotency_key,
            strategy_version=signal.strategy_version,
            signal_id=signal.id,
        )
        result = await broker.place_order(req)

        order = models.PaperOrder(
            idempotency_key=signal.idempotency_key,
            signal_id=signal.id,
            portfolio_id=portfolio.id,
            symbol=signal.symbol,
            exchange=signal.exchange,
            side=signal.signal_type,
            quantity=qty,
            requested_price=signal.price,
            fill_price=result.fill_price,
            status=result.status.value,
            rejection_reason=result.rejection_reason,
            stop_loss=signal.stop_loss,
            target=signal.target,
            target2=signal.target2,
            strategy_version=signal.strategy_version,
            brokerage=result.brokerage,
            charges=result.charges,
            slippage=result.slippage,
            broker_used=broker.name,
            filled_at=result.filled_at,
        )
        db.add(order)
        await db.flush()

        if not result.success:
            signal.rejection_reason = result.rejection_reason
            await db.commit()
            return {"status": "REJECTED", "reason": result.rejection_reason}

        self.risk.mark_seen(signal.idempotency_key)
        signal.acted_on = True
        signal.quantity = qty

        # Open position
        pos_side = "LONG" if signal.signal_type == "BUY" else "SHORT"
        notional = (result.fill_price or signal.price) * qty
        costs = result.brokerage + result.charges
        if pos_side == "LONG":
            portfolio.cash -= notional + costs
        else:
            # Short: credit proceeds minus costs
            portfolio.cash += notional - costs

        position = models.Position(
            portfolio_id=portfolio.id,
            symbol=signal.symbol,
            exchange=signal.exchange,
            side=pos_side,
            quantity=qty,
            entry_price=result.fill_price or signal.price,
            current_price=result.fill_price or signal.price,
            stop_loss=signal.stop_loss,
            target=signal.target,
            target2=signal.target2,
            strategy_version=signal.strategy_version,
            entry_signal_id=signal.id,
            entry_order_id=order.id,
            entry_reason=signal.reason,
            status="OPEN",
        )
        db.add(position)
        await self._audit(
            db,
            category="ORDER",
            action="PAPER_ORDER_FILLED",
            symbol=signal.symbol,
            signal=signal.signal_type,
            order_id=order.id,
            detail={
                "fill_price": result.fill_price,
                "broker": broker.name,
                "mode": "PAPER",
            },
        )
        await db.commit()
        return {
            "status": "FILLED",
            "order_id": order.id,
            "fill_price": result.fill_price,
            "broker": broker.name,
            "mode": "PAPER",
        }

    async def _close_position(
        self,
        db: AsyncSession,
        portfolio: models.Portfolio,
        position: models.Position,
        signal: models.Signal,
        reason: str,
    ) -> dict[str, Any]:
        broker = get_broker(
            slippage_bps=portfolio.slippage_bps,
            brokerage_per_order=portfolio.brokerage_per_order,
            stt_rate=portfolio.stt_rate,
            exchange_rate=portfolio.exchange_rate,
            gst_rate=portfolio.gst_rate,
            sebi_rate=portfolio.sebi_rate,
            stamp_duty_rate=portfolio.stamp_duty_rate,
        )
        assert_no_live_orders_in_paper(broker)
        side = OrderSide.SELL if position.side == "LONG" else OrderSide.BUY
        req = BrokerOrderRequest(
            symbol=position.symbol,
            exchange=position.exchange,
            side=side,
            quantity=position.quantity,
            price=signal.price,
            idempotency_key=signal.idempotency_key + ":exit",
            strategy_version=signal.strategy_version,
            signal_id=signal.id,
        )
        result = await broker.place_order(req)
        if not result.success:
            return {"status": "REJECTED", "reason": result.rejection_reason}

        fill = result.fill_price or signal.price
        if position.side == "LONG":
            gross = (fill - position.entry_price) * position.quantity
            portfolio.cash += fill * position.quantity
        else:
            gross = (position.entry_price - fill) * position.quantity
            portfolio.cash -= fill * position.quantity

        costs = result.brokerage + result.charges + result.slippage
        # Also account for entry costs approximately already deducted; exit costs:
        portfolio.cash -= result.brokerage + result.charges
        net = gross - costs
        pnl_pct = (net / (position.entry_price * position.quantity)) * 100 if position.entry_price else 0

        duration = 0
        if position.opened_at:
            opened = ensure_utc(position.opened_at) or utc_now()
            duration = int((utc_now() - opened).total_seconds())
        trade = models.Trade(
            portfolio_id=portfolio.id,
            position_id=position.id,
            symbol=position.symbol,
            exchange=position.exchange,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=fill,
            gross_pnl=round(gross, 2),
            net_pnl=round(net, 2),
            pnl_pct=round(pnl_pct, 4),
            brokerage=result.brokerage,
            charges=result.charges,
            slippage=result.slippage,
            stop_loss=position.stop_loss,
            target=position.target,
            entry_reason=position.entry_reason,
            exit_reason=reason,
            strategy_version=position.strategy_version,
            indicator_values=signal.indicator_values or {},
            entry_signal_id=position.entry_signal_id,
            exit_signal_id=signal.id,
            opened_at=position.opened_at,
            closed_at=utc_now(),
            duration_seconds=duration,
            is_backtest=False,
        )
        db.add(trade)

        order = models.PaperOrder(
            idempotency_key=signal.idempotency_key + ":exit",
            signal_id=signal.id,
            portfolio_id=portfolio.id,
            symbol=position.symbol,
            exchange=position.exchange,
            side="EXIT_" + ("SELL" if position.side == "LONG" else "BUY"),
            quantity=position.quantity,
            requested_price=signal.price,
            fill_price=fill,
            status="FILLED",
            strategy_version=signal.strategy_version,
            brokerage=result.brokerage,
            charges=result.charges,
            slippage=result.slippage,
            broker_used=broker.name,
            filled_at=result.filled_at,
        )
        db.add(order)

        position.status = "CLOSED"
        position.closed_at = utc_now()
        position.current_price = fill
        position.unrealized_pnl = 0

        portfolio.realized_pnl += net
        self.risk.record_realized(net)
        signal.acted_on = True

        await self._audit(
            db,
            category="TRADE",
            action="PAPER_POSITION_CLOSED",
            symbol=position.symbol,
            signal="EXIT",
            detail={"net_pnl": net, "gross_pnl": gross, "reason": reason},
        )
        await db.commit()
        return {"status": "CLOSED", "net_pnl": net, "trade_id": trade.id}

    async def _audit(
        self,
        db: AsyncSession,
        *,
        category: str,
        action: str,
        symbol: str | None = None,
        signal: str | None = None,
        order_id: int | None = None,
        detail: dict | None = None,
    ) -> None:
        db.add(
            models.AuditLog(
                category=category,
                action=action,
                symbol=symbol,
                signal=signal,
                order_id=order_id,
                detail=detail or {},
                user="system",
            )
        )
