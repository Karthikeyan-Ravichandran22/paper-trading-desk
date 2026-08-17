"""Broker abstraction — strategy never talks to Angel One order APIs directly."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class BrokerOrderRequest:
    symbol: str
    exchange: str
    side: OrderSide
    quantity: int
    price: float
    order_type: str = "MARKET"
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    target2: Optional[float] = None
    idempotency_key: str = ""
    strategy_version: str = ""
    signal_id: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerOrderResult:
    success: bool
    status: OrderStatus
    fill_price: Optional[float] = None
    brokerage: float = 0.0
    charges: float = 0.0
    slippage: float = 0.0
    broker_name: str = ""
    rejection_reason: Optional[str] = None
    filled_at: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)


class BrokerInterface(ABC):
    """Common interface for PaperBroker and LiveBroker."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def is_live(self) -> bool:
        ...

    @abstractmethod
    async def place_order(self, request: BrokerOrderRequest) -> BrokerOrderResult:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        ...
