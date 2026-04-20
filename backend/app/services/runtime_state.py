import os
import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class RuntimeStateService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._latest_tick: dict[str, Any] | None = None
        self._latest_tick_received_at: datetime | None = None
        self._tick_source: str = "none"
        self._trading_style: str = "Scalper"
        self._target_symbol: str = os.getenv("MT5_SYMBOL", "XAUUSD")
        self._ai_provider: str = "openai"
        self._ai_api_key: str | None = None
        self._latest_candles: dict[tuple[str, str], dict[str, Any]] = {}
        self._engine_status: dict[str, Any] | None = {
            "phase": "booting",
            "message": "Engine starting up.",
            "detail": "Waiting for the first analysis cycle.",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def set_tick(self, tick: dict[str, Any] | None) -> None:
        if tick is None:
            with self._lock:
                self._latest_tick = None
                self._latest_tick_received_at = None
                self._tick_source = "none"
            return

        incoming_source = tick.get("source", "").upper()
        local_received_at = datetime.now(timezone.utc)
        normalized_tick = dict(tick)
        if normalized_tick.get("received_at"):
            normalized_tick.setdefault("source_received_at", normalized_tick.get("received_at"))
        
        with self._lock:
            current_source = self._tick_source
            
            if incoming_source == "MT5":
                self._latest_tick = normalized_tick
                self._latest_tick_received_at = local_received_at
                self._tick_source = "MT5"
            elif incoming_source == "ALLTICK":
                if current_source != "MT5":
                    self._latest_tick = normalized_tick
                    self._latest_tick_received_at = local_received_at
                    self._tick_source = "ALLTICK"
                # If MT5 exists, ignore AllTick (MT5 always wins)
            else:
                self._latest_tick = normalized_tick
                self._latest_tick_received_at = local_received_at
                self._tick_source = incoming_source or "UNKNOWN"

    def get_tick(self) -> dict[str, Any] | None:
        with self._lock:
            if self._latest_tick is None:
                return None
            payload = dict(self._latest_tick)
            if self._latest_tick_received_at is not None:
                payload["received_at"] = self._latest_tick_received_at.isoformat()
            return payload

    def get_tick_source(self) -> str:
        with self._lock:
            return self._tick_source

    def set_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        source: str = "bridge-mt5",
    ) -> None:
        received_at = datetime.now(timezone.utc).isoformat()
        normalized = [
            {
                "time": candle.get("time"),
                "open": candle.get("open"),
                "high": candle.get("high"),
                "low": candle.get("low"),
                "close": candle.get("close"),
                "volume": candle.get("volume", 0),
            }
            for candle in candles
            if candle.get("time") is not None
        ]
        key = (symbol.upper(), timeframe)
        with self._lock:
            self._latest_candles[key] = {
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "source": source,
                "received_at": received_at,
                "candles": normalized,
            }

    def get_candles(self, *, symbol: str, timeframe: str) -> dict[str, Any] | None:
        key = (symbol.upper(), timeframe)
        with self._lock:
            payload = self._latest_candles.get(key)
            if payload is None:
                return None
            return {
                "symbol": payload["symbol"],
                "timeframe": payload["timeframe"],
                "source": payload["source"],
                "received_at": payload["received_at"],
                "candles": [dict(candle) for candle in payload.get("candles", [])],
            }

    def set_trading_style(self, style: str) -> None:
        with self._lock:
            self._trading_style = style

    def get_trading_style(self) -> str:
        with self._lock:
            return self._trading_style

    def set_target_symbol(self, symbol: str) -> None:
        with self._lock:
            self._target_symbol = symbol

    def get_target_symbol(self) -> str:
        with self._lock:
            return self._target_symbol

    def set_ai_preferences(self, provider: str | None = None, api_key: str | None = None) -> None:
        with self._lock:
            if provider:
                self._ai_provider = provider
            if api_key:
                self._ai_api_key = api_key

    def get_ai_preferences(self) -> tuple[str, str | None]:
        with self._lock:
            return self._ai_provider, self._ai_api_key

    def set_engine_status(
        self,
        *,
        phase: str,
        message: str,
        detail: str | None = None,
        symbol: str | None = None,
        trading_style: str | None = None,
        progress: int | float | None = None,
        current_gate: str | None = None,
        candidate_count: int | None = None,
        rejected_count: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        status: dict[str, Any] = {
            "phase": phase,
            "message": message,
            "detail": detail,
            "symbol": symbol,
            "trading_style": trading_style,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if progress is not None:
            status["progress"] = progress
        if current_gate:
            status["current_gate"] = current_gate
        if candidate_count is not None:
            status["candidate_count"] = candidate_count
        if rejected_count is not None:
            status["rejected_count"] = rejected_count
        status.update({key: value for key, value in extra.items() if value is not None})

        with self._lock:
            self._engine_status = status
        return dict(status)

    def get_engine_status(self) -> dict[str, Any] | None:
        with self._lock:
            if self._engine_status is None:
                return None
            return dict(self._engine_status)

    def snapshot(self) -> dict[str, Any]:
        tick = self.get_tick()
        with self._lock:
            candle_state = {
                f"{symbol}:{timeframe}": {
                    "source": payload.get("source"),
                    "received_at": payload.get("received_at"),
                    "count": len(payload.get("candles", [])),
                }
                for (symbol, timeframe), payload in self._latest_candles.items()
            }
            return {
                "trading_style": self._trading_style,
                "target_symbol": self._target_symbol,
                "latest_tick": tick,
                "latest_candles": candle_state,
                "ai_provider": self._ai_provider,
                "has_ai_key": bool(self._ai_api_key),
                "engine_status": dict(self._engine_status) if self._engine_status else None,
            }


runtime_state = RuntimeStateService()
