"""Angel One Paper Trading Dashboard — FastAPI entrypoint.

Launches in PAPER MODE by default. Live order APIs are hard-disabled.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.safety import current_mode_label
from app.db.seed import seed_database
from app.db.session import init_db
from app.services.broker.angel_one import angel_client
from app.services.market.data_service import market_data_service
from app.services.strategy.engine import signal_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("paper_trading")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Ensure data dir for SQLite
    if "sqlite" in settings.database_url:
        Path("data").mkdir(parents=True, exist_ok=True)

    await init_db()
    await seed_database()

    # Attempt Angel One login when credentials are present (market data only)
    if settings.angel_configured:
        login_result = await angel_client.login()
        if login_result.get("status"):
            logger.info("Angel One connected for market data (orders remain PAPER-only)")
            market_data_service._source = "ANGEL_ONE"
        else:
            logger.warning(
                "Angel One login failed — falling back to DEMO data: %s",
                login_result.get("message"),
            )
            market_data_service._source = "DEMO"
    else:
        logger.info("Angel One not fully configured — using DEMO market data")

    symbols = [s.strip() for s in settings.demo_symbols.split(",") if s.strip()]
    await market_data_service.start(symbols, timeframe="5m")
    await signal_engine.start()

    logger.info("=" * 60)
    logger.info("STARTED IN %s MODE", current_mode_label())
    logger.info("Live trading enabled flag: %s", settings.live_trading_enabled)
    logger.info("Market data source: %s", market_data_service.source)
    logger.info("=" * 60)

    yield

    await signal_engine.stop()
    await market_data_service.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="Paper-trading first Angel One + Pine strategy dashboard. LIVE orders disabled.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list + ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"ok": True, "mode": current_mode_label()}

    @app.websocket("/ws/live")
    async def ws_live(websocket: WebSocket):
        await websocket.accept()
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(event, payload):
            await queue.put({"event": event, "data": payload})

        market_data_service.subscribe(on_event)
        try:
            await websocket.send_json(
                {
                    "event": "hello",
                    "data": {
                        "mode": "PAPER",
                        "source": market_data_service.source,
                        "banner": "PAPER TRADING",
                    },
                }
            )
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=5.0)
                    await websocket.send_json(msg)
                except asyncio.TimeoutError:
                    # heartbeat + status
                    await websocket.send_json(
                        {
                            "event": "heartbeat",
                            "data": {
                                **market_data_service.status(),
                                "signal": signal_engine.status().get("last_signal"),
                                "mode": "PAPER",
                            },
                        }
                    )
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("WebSocket error")

    return app


app = create_app()
