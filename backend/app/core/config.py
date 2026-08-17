"""Application configuration — secrets stay server-side only."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Angel One Paper Trading Dashboard"
    app_env: str = "development"
    secret_key: str = "dev-secret-change-in-production"
    database_url: str = "sqlite+aiosqlite:///./data/paper_trading.db"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Critical safety defaults
    trading_mode: Literal["PAPER", "LIVE"] = "PAPER"
    live_trading_enabled: bool = False

    default_starting_capital: float = 100_000.0
    default_slippage_bps: float = 5.0
    default_brokerage_per_order: float = 20.0

    angel_api_key: str = ""
    angel_client_code: str = ""
    angel_password: str = ""
    angel_totp_secret: str = ""
    angel_feed_token: str = ""
    angel_jwt_token: str = ""
    angel_refresh_token: str = ""

    use_demo_market_data: bool = True
    demo_symbols: str = "NIFTY,BANKNIFTY,RELIANCE,TCS,INFY"

    admin_username: str = "trader"
    admin_password: str = "paper-trade-only"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def angel_configured(self) -> bool:
        return bool(self.angel_api_key and self.angel_client_code)

    @property
    def is_paper_mode(self) -> bool:
        """LIVE is never active unless explicitly enabled AND trading_mode=LIVE."""
        if not self.live_trading_enabled:
            return True
        return self.trading_mode != "LIVE"


@lru_cache
def get_settings() -> Settings:
    return Settings()
