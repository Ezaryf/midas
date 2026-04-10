from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

from app.api.ws.mt5_handler import manager
from app.core.loop import STYLE_CONFIG, is_high_impact_news_upcoming, is_trading_session_active
from app.schemas.contracts import (
    AnalysisBatchResponse,
    ErrorResponse,
    ExecutionResultResponse,
    HealthResponse,
    RiskCheckResponse,
)
from app.services.repositories import analytics_repository, order_repository, signal_repository
from app.services.runtime_state import runtime_state
from app.services.trading_state import trading_state


class ApplicationService:
    async def force_generate_signal(
        self,
        *,
        trading_style: str,
        api_key: str | None = None,
        ai_provider: str | None = None,
    ) -> AnalysisBatchResponse:
        from app.services.analysis_pipeline import TradingEngine

        trading_state.set_trading_style(trading_style)
        runtime_state.set_trading_style(trading_style)
        if api_key or ai_provider:
            runtime_state.set_ai_preferences(provider=ai_provider, api_key=api_key)
            if api_key:
                os.environ["AI_API_KEY"] = api_key
                os.environ["OPENAI_API_KEY"] = api_key
            if ai_provider:
                os.environ["AI_PROVIDER"] = ai_provider

        engine = TradingEngine(STYLE_CONFIG)
        return await engine.analyze(
            trading_style=trading_style,
            symbol=trading_state.target_symbol,
            session_active=is_trading_session_active(style=trading_style, symbol=trading_state.target_symbol),
            news_blocked=is_high_impact_news_upcoming(),
            risk_blocked=False,
            publish=True,
        )

    def set_trading_style(self, trading_style: str) -> dict[str, Any]:
        trading_state.set_trading_style(trading_style)
        runtime_state.set_trading_style(trading_style)
        return {"trading_style": trading_style}

    def set_target_symbol(self, target_symbol: str) -> dict[str, Any]:
        trading_state.set_target_symbol(target_symbol)
        runtime_state.set_target_symbol(target_symbol)
        return {"target_symbol": target_symbol}

    async def execute_signal(self, signal_data: dict[str, Any]) -> ExecutionResultResponse:
        connections = len(manager.active_connections)
        if connections == 0:
            return ExecutionResultResponse(
                status="warning",
                message="No MT5 bridge connected. Run: python backend/mt5_bridge.py",
                data={"connections": 0},
            )

        signal_id = str(uuid.uuid4())[:8]
        payload = dict(signal_data)
        payload["signal_id"] = signal_id

        await manager.broadcast_json({"type": "SIGNAL", "action": "PLACE_ORDER", "data": payload})

        for _ in range(50):
            await asyncio.sleep(0.1)
            ack = manager.get_ack(signal_id)
            if not ack:
                continue
            if ack.get("status") == "ok":
                return ExecutionResultResponse(
                    status="ok",
                    message=f"Order #{ack.get('ticket')} placed @ {ack.get('price')}",
                    data={
                        "ticket": ack.get("ticket"),
                        "price": ack.get("price"),
                    },
                )
            if ack.get("status") == "closed":
                return ExecutionResultResponse(
                    status="ok",
                    message=ack.get("message", "Position closed"),
                    data={"details": ack},
                )
            if ack.get("status") in {"skipped", "blocked"}:
                return ExecutionResultResponse(
                    status="warning",
                    message=ack.get("message", "Signal not executed"),
                    data={"details": ack},
                )
            return ExecutionResultResponse(
                status="error",
                message=ack.get("message", "Order failed"),
                data={"details": ack},
            )

        return ExecutionResultResponse(
            status="warning",
            message=f"Signal sent to {connections} bridge(s) but no confirmation received",
            data={"connections": connections},
        )

    def health(self) -> HealthResponse:
        from app.services.database import db

        bridge_connected = len(manager.active_connections) > 0
        runtime_snapshot = runtime_state.snapshot()
        latest_tick = runtime_state.get_tick() or manager.latest_tick or {}
        latest_price = latest_tick.get("bid") if isinstance(latest_tick, dict) else None
        latest_candles = runtime_snapshot.get("latest_candles", {})
        has_live_candles = bool(latest_candles)
        health_status = "ok" if bridge_connected and has_live_candles else "degraded" if bridge_connected else "ok"
        return HealthResponse(
            status=health_status,
            mt5_connected=bridge_connected,
            bridge_count=len(manager.active_connections),
            latest_price=latest_price,
            pending_signals=len(manager._pending_signals),
            database_enabled=db.is_enabled(),
            runtime_state=runtime_snapshot,
            message=(
                "Bridge connected with live tick/candle cache"
                if bridge_connected and has_live_candles
                else "Bridge connected but live candle cache is empty"
                if bridge_connected
                else "No bridge - run: python backend/mt5_bridge.py --auto-trade"
            ),
        )

    def account(self) -> dict[str, Any]:
        tick = runtime_state.get_tick() or manager.latest_tick
        if not tick:
            return {"connected": False}
        return {"connected": True, **tick}

    def signal_history(self, limit: int = 50) -> dict[str, Any]:
        return {"signals": signal_repository.recent(limit=limit)}

    def order_history(self, status: str = "all") -> dict[str, Any]:
        if status == "open":
            return {"orders": order_repository.open_orders()}
        return {"orders": []}

    def performance(self, period: str = "ALL_TIME") -> dict[str, Any]:
        return {"metrics": analytics_repository.performance(period=period)}

    def equity_curve(self, days: int = 30) -> dict[str, Any]:
        return {"data": analytics_repository.equity_curve(days=days)}

    def risk_check(
        self,
        *,
        direction: str,
        symbol: str | None = None,
        volume: float | None = None,
        price: float | None = None,
    ) -> RiskCheckResponse:
        from app.services.risk_manager import get_risk_manager

        risk_manager = get_risk_manager()
        if not risk_manager:
            return RiskCheckResponse(
                status="error",
                allowed=False,
                reason="Risk manager not available",
                symbol=symbol,
                direction=direction,
                volume=volume,
                price=price,
            )

        effective_symbol = symbol or runtime_state.get_target_symbol()
        effective_price = price
        if effective_price is None:
            latest_tick = runtime_state.get_tick()
            if latest_tick and latest_tick.get("symbol") == effective_symbol:
                effective_price = latest_tick.get("ask") if direction == "BUY" else latest_tick.get("bid")

        can_trade, reason = risk_manager.can_open_position(
            direction=direction,
            symbol=effective_symbol,
            volume=volume,
            price=effective_price,
        )
        return RiskCheckResponse(
            status="ok" if can_trade else "warning",
            allowed=can_trade,
            reason=reason,
            symbol=effective_symbol,
            direction=direction,
            volume=volume,
            price=effective_price,
        )


application_service = ApplicationService()
