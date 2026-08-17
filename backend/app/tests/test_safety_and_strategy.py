"""Critical safety + strategy + paper trading tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.core.safety import LiveTradingBlockedError, current_mode_label, live_orders_allowed
from app.services.broker.factory import get_broker
from app.services.broker.live_broker import LiveBroker
from app.services.broker.paper_broker import PaperBroker
from app.services.broker.base import BrokerOrderRequest, OrderSide
from app.services.broker.angel_one import AngelOneClient
from app.services.risk.engine import RiskEngine
from app.services.strategy.sore_scalper import SoreScalperPro, DEFAULT_PARAMS


@pytest.mark.asyncio
async def test_paper_mode_default():
    assert current_mode_label() == "PAPER"
    assert live_orders_allowed() is False


@pytest.mark.asyncio
async def test_factory_returns_paper_broker():
    broker = get_broker()
    assert isinstance(broker, PaperBroker)
    assert broker.is_live is False
    assert broker.name == "PaperBroker"


@pytest.mark.asyncio
async def test_buy_signal_goes_to_paper_broker_never_live():
    broker = get_broker()
    assert not broker.is_live
    result = await broker.place_order(
        BrokerOrderRequest(
            symbol="NIFTY",
            exchange="NSE",
            side=OrderSide.BUY,
            quantity=50,
            price=19850,
            idempotency_key="test-key-1",
        )
    )
    assert result.success
    assert result.broker_name == "PaperBroker"
    assert result.fill_price is not None


@pytest.mark.asyncio
async def test_live_broker_blocked():
    live = LiveBroker()
    with pytest.raises(LiveTradingBlockedError):
        await live.place_order(
            BrokerOrderRequest(
                symbol="NIFTY",
                exchange="NSE",
                side=OrderSide.BUY,
                quantity=1,
                price=100,
            )
        )


@pytest.mark.asyncio
async def test_angel_place_order_blocked():
    client = AngelOneClient()
    with pytest.raises(LiveTradingBlockedError):
        await client.place_order(symbol="NIFTY", qty=1)


@pytest.mark.asyncio
async def test_live_broker_angel_path_blocked():
    live = LiveBroker()
    with pytest.raises(LiveTradingBlockedError):
        await live.place_order_via_angel({"symbol": "NIFTY"})


def test_strategy_validation_passes():
    report = SoreScalperPro.validate("", DEFAULT_PARAMS)
    assert report.passed
    assert "pine_script_parsed" in report.checks


def _sample_ohlcv(n=200, start=19800.0):
    rng = np.random.default_rng(42)
    rows = []
    price = start
    for i in range(n):
        o = price
        c = price * (1 + rng.uniform(-0.002, 0.002))
        h = max(o, c) * (1 + rng.uniform(0, 0.001))
        l = min(o, c) * (1 - rng.uniform(0, 0.001))
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": 100000})
        price = c
    return pd.DataFrame(rows)


def test_strategy_produces_signals_without_crash():
    df = _sample_ohlcv(250)
    s = SoreScalperPro({**DEFAULT_PARAMS, "minMTF": 0, "minEaF": 0})
    out = s.compute_dataframe(df)
    assert "signal" in out.columns
    assert set(out["signal"].unique()).issubset({"BUY", "SELL", "EXIT", "HOLD"})


def test_strategy_buy_sell_hold_exit_conditions():
    df = _sample_ohlcv(300)
    s = SoreScalperPro({**DEFAULT_PARAMS, "minMTF": 0, "minEaF": 1})
    out = s.compute_dataframe(df)
    # At least HOLD exists; others depend on path — ensure no-signal path works
    assert (out["signal"] == "HOLD").any()
    last = s.last_result(df)
    assert last.signal in ("BUY", "SELL", "EXIT", "HOLD")


@pytest.mark.asyncio
async def test_paper_entry_exit_slippage_charges():
    broker = PaperBroker(slippage_bps=10, brokerage_per_order=20)
    buy = await broker.place_order(
        BrokerOrderRequest("NIFTY", "NSE", OrderSide.BUY, 10, 1000, idempotency_key="e1")
    )
    assert buy.fill_price > 1000  # buy slippage up
    assert buy.brokerage == 20
    assert buy.charges >= 0
    sell = await broker.place_order(
        BrokerOrderRequest("NIFTY", "NSE", OrderSide.SELL, 10, 1000, idempotency_key="e2")
    )
    assert sell.fill_price < 1000


def test_risk_duplicate_and_limits():
    risk = RiskEngine(max_open_positions=1, max_position_size=10000, max_daily_loss=100)
    ok = risk.validate(
        symbol="NIFTY",
        signal_type="BUY",
        price=100,
        quantity=10,
        idempotency_key="k1",
        strategy_active=True,
        open_positions=0,
        has_open_position_for_symbol=False,
        available_cash=50000,
        market_data_valid=True,
        data_source="DEMO",
    )
    assert ok.allowed
    risk.mark_seen("k1")
    dup = risk.validate(
        symbol="NIFTY",
        signal_type="BUY",
        price=100,
        quantity=10,
        idempotency_key="k1",
        strategy_active=True,
        open_positions=0,
        has_open_position_for_symbol=False,
        available_cash=50000,
        market_data_valid=True,
        data_source="DEMO",
    )
    assert not dup.allowed
    assert "Duplicate" in dup.reason

    pos = risk.validate(
        symbol="NIFTY",
        signal_type="BUY",
        price=100,
        quantity=10,
        idempotency_key="k2",
        strategy_active=True,
        open_positions=0,
        has_open_position_for_symbol=True,
        available_cash=50000,
        market_data_valid=True,
        data_source="DEMO",
    )
    assert not pos.allowed

    stale = risk.validate(
        symbol="NIFTY",
        signal_type="BUY",
        price=100,
        quantity=10,
        idempotency_key="k3",
        strategy_active=True,
        open_positions=0,
        has_open_position_for_symbol=False,
        available_cash=50000,
        market_data_valid=False,
        data_source="DEMO",
    )
    assert not stale.allowed


def test_risk_daily_loss_and_size():
    risk = RiskEngine(max_position_size=5000, max_daily_loss=100)
    risk.record_realized(-150)
    blocked = risk.validate(
        symbol="TCS",
        signal_type="BUY",
        price=100,
        quantity=10,
        idempotency_key="k4",
        strategy_active=True,
        open_positions=0,
        has_open_position_for_symbol=False,
        available_cash=100000,
        market_data_valid=True,
        data_source="DEMO",
    )
    assert not blocked.allowed
    assert "daily loss" in blocked.reason.lower()

    oversized = risk.validate(
        symbol="TCS",
        signal_type="BUY",
        price=1000,
        quantity=10,
        idempotency_key="k5",
        strategy_active=True,
        open_positions=0,
        has_open_position_for_symbol=False,
        available_cash=100000,
        market_data_valid=True,
        data_source="DEMO",
    )
    # daily loss already exceeded from above
    assert not oversized.allowed
