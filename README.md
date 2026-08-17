# Paper Trading Dashboard

Production-oriented **paper-trading first** platform for Angel One SmartAPI market data + SORE Scalper Pro (Pine v7.60) signal execution.

## Critical safety

- Default mode: **PAPER**
- **LIVE MODE is disabled** even if Angel One is connected
- Strategy → Risk → Order Manager → **PaperBroker** only
- `LiveBroker` / Angel One `placeOrder` raise `LiveTradingBlockedError` during paper phase
- Prominent **PAPER TRADING / PAPER MODE** banners in the UI

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React + TypeScript + Vite + lightweight-charts |
| Backend | Python FastAPI |
| DB | SQLite (default) / set `DATABASE_URL` for PostgreSQL |
| Broker | PaperBroker (active) · LiveBroker (locked) · Angel One market-data client |

## Quick start

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # or backend/.env
mkdir -p data
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### 3. Tests

```bash
cd backend
source .venv/bin/activate
pytest app/tests -v
```

## Environment variables

See `.env.example`. Important:

- `TRADING_MODE=PAPER`
- `LIVE_TRADING_ENABLED=false`
- `USE_DEMO_MARKET_DATA=true` until Angel One credentials are set
- Angel One secrets (`ANGEL_API_KEY`, `ANGEL_CLIENT_CODE`, `ANGEL_PASSWORD`, `ANGEL_TOTP_SECRET`) — **server only**

Never put API secrets in frontend code.

## SORE Scalper Pro

Your Pine Script (**SORE Scalper Pro — Automation & Visual Edition v7.60**) is ported to:

`backend/app/services/strategy/sore_scalper.py`

Supported executable logic:

- EMA / Supertrend / HalfTrend
- Oscillator (MACD), EA filters (EMA+MACD+CCI+RSI)
- Neon candle patterns
- Dynamic ATR TP (ADX volatility multiplier)
- MTF gate (when multi-TF series provided; otherwise disclosed fallback)
- Entries: `validBuy` / `validSell` with flat-only `tradeState`
- Exits: SL, 1m trend flip, trend reverse, optional stoch

**Explicitly flagged (visual / approximate):**

- Pine `table` dashboards, `line`/`label` drawings, `plot*` overlays
- `alert()` webhooks (replaced by internal signal + notification engine)
- Exact `request.security` MTF parity needs multi-timeframe candle feeds

## 7-day paper test

On first boot the app starts a **7-DAY PAPER TEST** experiment. After 7 days it auto-generates a report. You can also open **Performance → Generate Snapshot Report** anytime.

## Architecture

```
Market Data → Candles → Indicators → SORE Strategy → Signal Engine
    → Risk Engine → Order Manager → PaperBroker → Portfolio → Analytics → Dashboard
```

## API highlights

- `GET /api/status` — system status
- `GET /api/watchlist` — quotes
- `GET /api/candles/{symbol}` — OHLCV + markers
- `GET /api/signals` / `GET /api/portfolio` / `GET /api/trades`
- `POST /api/backtest` — labelled BACKTEST (isolated from paper account)
- `POST /api/safety/probe-live-order` — proves live order path is blocked
- `WS /ws/live` — tick + heartbeat stream

## Disclaimer

Paper / demo / backtest results are **not** a guarantee of live performance. Simulated charges and slippage are configurable assumptions, not identical to Angel One fills.
