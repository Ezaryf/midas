import os
from datetime import datetime, timezone
from threading import Lock
from typing import Any


class RuntimeStateService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._latest_tick: dict[str, Any] | None = None
        self._latest_tick_received_at: datetime | None = None
        self._trading_style: str = "Scalper"
        self._target_symbol: str = os.getenv("MT5_SYMBOL", "XAUUSD")
        self._ai_provider: str = "openai"
        self._ai_api_key: str | None = None
        self._latest_candles: dict[tuple[str, str], dict[str, Any]] = {}

    def set_tick(self, tick: dict[str, Any] | None) -> None:
        with self._lock:
            self._latest_tick = dict(tick or {})
            self._latest_tick_received_at = datetime.now(timezone.utc) if tick else None

    def get_tick(self) -> dict[str, Any] | None:
        with self._lock:
            if self._latest_tick is None:
                return None
            payload = dict(self._latest_tick)
            if self._latest_tick_received_at is not None:
                payload.setdefault("received_at", self._latest_tick_received_at.isoformat())
            return payload

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
            }


runtime_state = RuntimeStateService()
