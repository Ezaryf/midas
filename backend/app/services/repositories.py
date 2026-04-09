from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.signal import TradeSignal
from app.services.database import db


@dataclass
class SignalPersistencePayload:
    signal: TradeSignal
    indicators: dict[str, Any]
    calendar_events: list[Any]
    current_price: float
    trend: str
    ai_provider: str
    ai_model: str
    regime_summary: str | None = None


class SignalRepository:
    def save(self, payload: SignalPersistencePayload) -> str:
        return db.save_signal(
            signal=payload.signal,
            indicators=payload.indicators,
            calendar_events=payload.calendar_events,
            current_price=payload.current_price,
            trend=payload.trend,
            ai_provider=payload.ai_provider,
            ai_model=payload.ai_model,
            regime_summary=payload.regime_summary,
        )

    def recent(self, limit: int = 10) -> list[Any]:
        return db.get_recent_signals(limit=limit)


class OrderRepository:
    def open_orders(self) -> list[Any]:
        return db.get_open_orders()


class AnalyticsRepository:
    def performance(self, period: str = "ALL_TIME") -> dict[str, Any]:
        db.calculate_performance_metrics(period=period)
        return db.get_performance_metrics(period=period)

    def equity_curve(self, days: int = 30) -> list[Any]:
        return db.get_equity_curve(days=days)


class RuntimeStateRepository:
    def enabled(self) -> bool:
        return db.is_enabled()


signal_repository = SignalRepository()
order_repository = OrderRepository()
analytics_repository = AnalyticsRepository()
runtime_state_repository = RuntimeStateRepository()
