# Deploy (PAPER MODE)

Repo: https://github.com/Karthikeyan-Ravichandran22/paper-trading-desk

## Important
- App starts in **PAPER MODE**
- `LIVE_TRADING_ENABLED=false`
- Never commit Angel One secrets

## Render (free web URL)

1. Go to https://dashboard.render.com
2. **New** → **Web Service** → connect this GitHub repo
3. Runtime: **Docker**
4. Dockerfile path: `Dockerfile.web`
5. Add environment variables:

```
TRADING_MODE=PAPER
LIVE_TRADING_ENABLED=false
USE_DEMO_MARKET_DATA=false
ANGEL_API_KEY=...
ANGEL_CLIENT_CODE=...
ANGEL_PASSWORD=...
ANGEL_TOTP_SECRET=...
SECRET_KEY=any-long-random-string
DEFAULT_STARTING_CAPITAL=100000
```

6. Deploy
7. Copy the Render service outbound IP / static outbound IP
8. In Angel One SmartAPI app settings, set **Primary Static IP** to that Render IP

## Local run
See root `README.md`.
