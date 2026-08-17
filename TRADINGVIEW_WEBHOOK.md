# How to get features from your TradingView Pine strategy

Your chart panels (WAIT / BUY / SELL, MTF Gate, Entry / Stop-Loss / TP1 / TP2) are **features**.  
To send them into the paper desk (or read the same values from the app), use one of the options below.

Live app: **https://paper-trading-desk.onrender.com**

---

## Option A (best): TradingView Alert → Webhook

TradingView cannot “export the table” directly. It **can** fire an alert when your Pine `alert()` runs, and POST JSON to your app.

### 1. Webhook URL

```text
https://paper-trading-desk.onrender.com/api/webhook/tradingview
```

### 2. Create the alert on TradingView

1. Open `MCX:CRUDEOIL1!` on **5m** with **SQRE / SORE Scalper Pro**.
2. Click **Alert** (clock).
3. Condition: **Any alert() function call** (or your script’s buy/sell alert).
4. Notifications → enable **Webhook URL** → paste the URL above.
5. Message must be **valid JSON** (one object). Example:

```json
{"symbol":"{{ticker}}","action":"BUY","price":{{close}},"sl":0,"tp":0,"tp2":0,"timeframe":"5m"}
```

If your Pine already builds JSON inside `alert(...)`, leave the message as that JSON (or `{{strategy.order.alert_message}}` when using strategy alerts).

Accepted fields (aliases work too):

| Field | Meaning |
|-------|---------|
| `symbol` / `ticker` | e.g. `CRUDEOIL1!` |
| `action` / `signal` / `side` | `BUY`, `SELL`, or `EXIT` |
| `price` / `close` / `ep` | entry / signal price |
| `sl` / `stop` / `stop_loss` | stop-loss |
| `tp` / `tp1` / `target` | take-profit 1 |
| `tp2` / `target2` | take-profit 2 |
| `quantity` | optional lots |
| `timeframe` | e.g. `5m` |

### 3. What the app does

- Saves the signal
- Places a **PAPER** order only
- Never places a live Angel One order from this webhook

### 4. Quick test (without waiting for a chart signal)

```bash
curl -X POST https://paper-trading-desk.onrender.com/api/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"symbol":"CRUDEOIL","action":"BUY","price":7912,"sl":7880,"tp":7940,"tp2":7960,"timeframe":"5m"}'
```

You should see the paper desk update (signal / order / audit).

**Note:** Webhooks require a TradingView plan that includes webhook alerts.

---

## Option B: Read features from the app API

The app runs the same SORE Scalper logic on MCX CRUDEOIL candles and exposes the panel-style features:

```text
https://paper-trading-desk.onrender.com/api/features/current?symbol=CRUDEOIL&timeframe=5m
```

Example response fields: `status` (WAIT / BUY READY / …), `mtf_gate`, `entry`, `stop_loss`, `tp1`, `tp2`, `trend`, `volatility_mult`.

The dashboard **Live Strategy** panel also shows these under **CHART FEATURES**.

---

## Pine tip: alert JSON with your real SL/TP

In Pine, when you set entry/SL/TP, fire:

```pine
alert('{"symbol":"' + syminfo.ticker + '","action":"BUY","price":' + str.tostring(ep) + ',"sl":' + str.tostring(sl) + ',"tp":' + str.tostring(tp1) + ',"tp2":' + str.tostring(tp2) + ',"timeframe":"5m"}', alert.freq_once_per_bar_close)
```

Use `"SELL"` for short signals and `"EXIT"` to close.

---

## Important

- Still **PAPER MODE** only
- Keep chart timeframe **5m** to match the app
- Free Render may sleep; the keep-awake GitHub Action helps
