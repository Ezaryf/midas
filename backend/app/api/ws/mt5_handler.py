from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
from collections import deque

from app.services.runtime_state import runtime_state
from app.services.trading_state import trading_state

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter()


class FrontendConnectionManager:
    """Manages browser frontend WebSocket connections (read-only)."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Frontend connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Frontend disconnected. Total: {len(self.active_connections)}")

    async def broadcast_json(self, data: dict):
        """Broadcast data to all frontend connections."""
        if not self.active_connections:
            return
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(data)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)


frontend_manager = FrontendConnectionManager()


class MT5ConnectionManager:
    _SIGNAL_ACKS_MAX_SIZE = 100
    _SIGNAL_ACKS_TTL_SECONDS = 300

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.latest_tick: dict | None = None
        # Buffer last 10 signals so bridge gets them on reconnect
        self._pending_signals: deque[dict] = deque(maxlen=10)
        # Track signal acknowledgments: signal_id -> {"status": "ok"|"error", "message": str, "timestamp": float}
        self._signal_acks: dict[str, dict] = {}
        # Runtime trading style — set by frontend, read by loop
        self.trading_style: str | None = None

    def _cleanup_signal_acks(self):
        """Remove old signal acknowledgments to prevent memory leak."""
        import time
        now = time.time()
        expired_keys = [
            sid for sid, data in self._signal_acks.items()
            if now - data.get("timestamp", 0) > self._SIGNAL_ACKS_TTL_SECONDS
        ]
        for sid in expired_keys:
            del self._signal_acks[sid]
        
        # If still too large, remove oldest entries
        if len(self._signal_acks) > self._SIGNAL_ACKS_MAX_SIZE:
            sorted_keys = sorted(self._signal_acks.keys(), key=lambda k: self._signal_acks[k].get("timestamp", 0))
            for sid in sorted_keys[:len(self._signal_acks) - self._SIGNAL_ACKS_MAX_SIZE]:
                del self._signal_acks[sid]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired signal acks")

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("MT5 local agent connected.")

        # Replay any pending signals to the newly connected bridge
        if self._pending_signals:
            logger.info(f"Replaying {len(self._pending_signals)} pending signal(s) to new connection.")
            # Copy deque before iterating to avoid "deque mutated during iteration" error
            pending = list(self._pending_signals)
            for signal in pending:
                try:
                    await websocket.send_json(signal)
                except Exception:
                    pass
            self._pending_signals.clear()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("MT5 local agent disconnected.")

    async def broadcast_json(self, data: dict):
        """Sends a JSON payload to all active connections."""
        import math
        def sanitize_json_payload(obj):
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            elif isinstance(obj, dict):
                return {k: sanitize_json_payload(v) for k, v in obj.items()}
            elif isinstance(obj, list) or isinstance(obj, tuple):
                return [sanitize_json_payload(v) for v in obj]
            return obj

        sanitized_data = sanitize_json_payload(data)

        # Always broadcast to frontend (read-only) - even without bridge!
        if frontend_manager.active_connections:
            try:
                await frontend_manager.broadcast_json(sanitized_data)
            except Exception:
                pass  # Frontend disconnected, skip

        # Bridge-specific messages only when bridge is connected
        if not self.active_connections:
            # No bridge connected — queue the signal for when it reconnects
            if sanitized_data.get("type") == "SIGNAL":
                self._pending_signals.append(sanitized_data)
                logger.warning("No bridge connected — signal queued for next connection.")
            return

        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(sanitized_data)
            except Exception as e:
                # Connection closed or sending on closed WebSocket
                logger.warning(f"Failed to send to client, marking dead: {e}")
                dead.append(conn)

        for conn in dead:
            self.disconnect(conn)

    def store_ack(self, signal_id: str, ack_data: dict):
        """Store acknowledgment from bridge for a signal execution."""
        import time
        self._cleanup_signal_acks()
        ack_data["timestamp"] = time.time()
        self._signal_acks[signal_id] = ack_data
        logger.info(f"ACK received for signal {signal_id}: {ack_data.get('status')}")

    def get_ack(self, signal_id: str) -> dict | None:
        """Retrieve acknowledgment for a signal."""
        return self._signal_acks.get(signal_id)

    async def process_incoming_data(self, data: dict):
        """Process incoming messages from MT5 bridge."""
        msg_type = data.get("type")
        
        if msg_type == "TICK":
            # Price update from MT5
            tick_data = data.get("data", {})
            symbol = tick_data.get("symbol")
            if symbol and symbol != runtime_state.get_target_symbol():
                runtime_state.set_target_symbol(symbol)
                trading_state.set_target_symbol(symbol)
                logger.info(f"Target symbol synced to: {symbol}")

            self.latest_tick = tick_data
            runtime_state.set_tick(self.latest_tick)
            await self.broadcast_json({"type": "TICK", "data": self.latest_tick})

        elif msg_type == "CANDLES":
            candle_data = data.get("data", {})
            symbol = candle_data.get("symbol")
            timeframe = candle_data.get("timeframe")
            candles = candle_data.get("candles", [])
            if symbol and timeframe and candles:
                if symbol != runtime_state.get_target_symbol():
                    runtime_state.set_target_symbol(symbol)
                    trading_state.set_target_symbol(symbol)
                    logger.info(f"Target symbol synced from candle stream to: {symbol}")
                runtime_state.set_candles(
                    symbol=symbol,
                    timeframe=timeframe,
                    candles=candles,
                    source=candle_data.get("source", "bridge-mt5"),
                )

        elif msg_type == "ACK":
            # Acknowledgment of signal execution
            signal_id = data.get("signal_id")
            if signal_id:
                self.store_ack(signal_id, data)
        
        elif msg_type == "PONG":
            # Heartbeat response
            pass


manager = MT5ConnectionManager()


# Frontend router for browser clients
frontend_router = APIRouter()


@router.websocket("/mt5")
async def mt5_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await websocket.receive_text()
            except (RuntimeError, WebSocketDisconnect):
                # WebSocket disconnected — exit gracefully
                break
            try:
                payload = json.loads(data)
                await manager.process_incoming_data(payload)
            except json.JSONDecodeError:
                logger.error("Failed to decode JSON from MT5 agent")
    except WebSocketDisconnect:
        pass  # Already handled above
    finally:
        manager.disconnect(websocket)


@frontend_router.websocket("/frontend")
async def frontend_endpoint(websocket: WebSocket):
    """Dedicated WebSocket endpoint for browser frontend."""
    await frontend_manager.connect(websocket)
    try:
        while True:
            try:
                data = await websocket.receive_text()
            except (RuntimeError, WebSocketDisconnect):
                # WebSocket disconnected — exit gracefully
                break
            try:
                payload = json.loads(data)
                # Frontend is read-only, so we don't process incoming messages
                # Just log ping/pong for heartbeat
                if payload.get("type") == "PING":
                    await websocket.send_json({"type": "PONG"})
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        pass  # Already handled above
    finally:
        frontend_manager.disconnect(websocket)
