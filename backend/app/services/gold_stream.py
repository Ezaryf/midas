import os
import json
import logging
import asyncio
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import websockets
from websockets.asyncio.client import connect as ws_connect

from app.services.runtime_state import runtime_state

logger = logging.getLogger(__name__)


class GoldStreamService:
    _instance: "GoldStreamService | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "GoldStreamService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self.token: str = os.getenv("ALLTICK_TOKEN", "")
        self.enabled: bool = os.getenv("ALLTICK_ENABLED", "false").lower() == "true"
        self.ws_url: str = f"wss://quote.alltick.co/quote-b-ws-api?token={self.token}"
        self.symbol: str = "GOLD"

        self.running: bool = False
        self._task: asyncio.Task | None = None
        self.reconnect_delay: float = 1.0
        self.max_reconnect_delay: float = 60.0

        logger.info(f"GoldStreamService initialized: enabled={self.enabled}, token={'*' * 8}")

    def start(self) -> None:
        if not self.enabled:
            logger.info("AllTick stream disabled via ALLTICK_ENABLED=false")
            return

        if not self.token:
            logger.warning("AllTick token not configured - skipping secondary stream")
            return

        if self.running:
            logger.warning("GoldStream already running")
            return

        self.running = True
        self.reconnect_delay = 1.0

        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run())
            finally:
                loop.close()

        self._task = threading.Thread(target=run_async, daemon=True, name="GoldStream")
        self._task.start()
        logger.info("AllTick gold stream started")

    def stop(self) -> None:
        self.running = False
        if self._task and self._task.is_alive():
            self._task.join(timeout=5)
        logger.info("AllTick gold stream stopped")

    async def _run(self) -> None:
        while self.running:
            try:
                logger.info("Connecting to AllTick WebSocket...")
                async with ws_connect(
                    self.ws_url,
                    ping_interval=10,
                    ping_timeout=5,
                ) as ws:
                    logger.info("AllTick WebSocket connected")
                    self.reconnect_delay = 1.0

                    await self._subscribe(ws)
                    await self._listen(ws)

            except Exception as e:
                logger.error(f"AllTick WebSocket error: {e}")

            if self.running:
                logger.info(f"Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

    async def _subscribe(self, ws) -> None:
        subscribe_msg = {
            "cmd_id": 22004,
            "seq_id": int(time.time() * 1000),
            "trace": str(uuid.uuid4()),
            "data": {
                "symbol_list": [{"code": self.symbol}]
            }
        }
        await ws.send(json.dumps(subscribe_msg))
        logger.info(f"Subscribed to AllTick symbol: {self.symbol}")

    async def _listen(self, ws) -> None:
        heartbeat_task = asyncio.create_task(self._heartbeat(ws))

        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                    cmd_id = data.get("cmd_id")

                    if cmd_id == 22998:
                        self._handle_tick(data.get("data", {}))
                    elif cmd_id == 22005:
                        logger.debug("AllTick subscription confirmed")
                    elif cmd_id == 1001:
                        logger.warning(f"AllTick auth error: {data.get('msg')}")
                    else:
                        logger.debug(f"AllTick message: cmd_id={data.get('cmd_id')}")

                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse AllTick message: {message[:100]}")
                except Exception as e:
                    logger.error(f"Error processing AllTick message: {e}")

        except Exception as e:
            logger.error(f"AllTick listener error: {e}")
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self, ws) -> None:
        while self.running:
            try:
                await ws.send(json.dumps({"cmd_id": 1003, "trace": str(uuid.uuid4())}))
            except Exception as e:
                logger.debug(f"Heartbeat error: {e}")
            await asyncio.sleep(10)

    def _handle_tick(self, data: dict[str, Any]) -> None:
        try:
            price = float(data.get("price", 0))
            if price <= 0:
                return

            tick_time_ms = data.get("tick_time", "")
            if tick_time_ms:
                try:
                    tick_time = datetime.fromtimestamp(int(tick_time_ms) / 1000)
                except (ValueError, OSError):
                    tick_time = datetime.now()
            else:
                tick_time = datetime.now()

            tick_data = {
                "symbol": "XAUUSD",
                "bid": round(price, 2),
                "ask": round(price, 2),
                "last": round(price, 2),
                "price": round(price, 2),
                "time": tick_time.isoformat(),
                "source": "ALLTICK",
                "volume": int(data.get("volume", 0)),
                "received_at": datetime.now(timezone.utc).isoformat(),
            }

            runtime_state.set_tick(tick_data)
            logger.debug(f"AllTick tick: ${price:.2f}")

        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse AllTick tick data: {e}")


_gold_stream_instance: GoldStreamService | None = None


def get_gold_stream() -> GoldStreamService:
    global _gold_stream_instance
    if _gold_stream_instance is None:
        _gold_stream_instance = GoldStreamService()
    return _gold_stream_instance


def start_gold_stream() -> None:
    get_gold_stream().start()


def stop_gold_stream() -> None:
    if _gold_stream_instance:
        _gold_stream_instance.stop()