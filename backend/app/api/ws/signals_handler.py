from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
from collections import deque
from app.services.runtime_state import runtime_state

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter()


def sanitize_json_payload(obj):
    import math

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_json_payload(v) for k, v in obj.items()}
    if isinstance(obj, list) or isinstance(obj, tuple):
        return [sanitize_json_payload(v) for v in obj]
    return obj


class FrontendConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.latest_tick: dict | None = None
        self.latest_market_state: dict | None = None
        self.latest_signal_batch: dict | None = None
        self.latest_signal: dict | None = None
        self.latest_execution_ack: dict | None = None
        self.latest_engine_status: dict | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("Frontend client connected.")

        latest_tick = self.latest_tick or runtime_state.get_tick()
        replay_payloads: list[dict] = []
        if latest_tick:
            self.latest_tick = latest_tick
            replay_payloads.append({"type": "TICK", "data": latest_tick})
            logger.info(f"[DEBUG] Replaying TICK on connect: bid={latest_tick.get('bid')}, symbol={latest_tick.get('symbol')}")
        if self.latest_market_state:
            replay_payloads.append({"type": "MARKET_STATE", "data": self.latest_market_state})
            logger.info(f"[DEBUG] Replaying MARKET_STATE on connect")
        if self.latest_signal_batch:
            replay_payloads.append({"type": "SIGNAL_BATCH", "data": self.latest_signal_batch})
            logger.info(f"[DEBUG] Replaying SIGNAL_BATCH on connect: primary={self.latest_signal_batch.get('primary', {}).get('direction')}")
        if self.latest_signal:
            replay_payloads.append({"type": "SIGNAL", "data": self.latest_signal})
            logger.info(f"[DEBUG] Replaying SIGNAL on connect: direction={self.latest_signal.get('direction')}")
        if self.latest_execution_ack:
            replay_payloads.append({"type": "EXECUTION_ACK", "data": self.latest_execution_ack})
        latest_engine_status = self.latest_engine_status or runtime_state.get_engine_status()
        if latest_engine_status:
            self.latest_engine_status = latest_engine_status
            replay_payloads.append({"type": "ENGINE_STATUS", "data": latest_engine_status})
            logger.info(f"[DEBUG] Replaying ENGINE_STATUS on connect: phase={latest_engine_status.get('phase')}")

        logger.info(f"[DEBUG] Total replay payloads: {len(replay_payloads)}")

        for payload in replay_payloads:
            try:
                await websocket.send_json(sanitize_json_payload(payload))
            except Exception:
                pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("Frontend client disconnected.")

    async def broadcast_json(self, data: dict):
        sanitized_data = sanitize_json_payload(data)
        msg_type = sanitized_data.get("type")
        client_count = len(self.active_connections)
        logger.info(f"[DEBUG] broadcast_json: type={msg_type}, clients={client_count}")
        
        if msg_type == "TICK":
            tick_data = sanitized_data.get("data")
            if isinstance(tick_data, dict):
                self.latest_tick = tick_data
                logger.info(f"[DEBUG] TICK stored in manager: bid={tick_data.get('bid')}, symbol={tick_data.get('symbol')}")
        elif msg_type == "MARKET_STATE":
            market_state = sanitized_data.get("data")
            if isinstance(market_state, dict):
                self.latest_market_state = market_state
        elif msg_type == "SIGNAL_BATCH":
            signal_batch = sanitized_data.get("data")
            if isinstance(signal_batch, dict):
                self.latest_signal_batch = signal_batch
                logger.info(f"[DEBUG] SIGNAL_BATCH stored: primary_direction={signal_batch.get('primary', {}).get('direction')}")
        elif msg_type == "SIGNAL":
            signal = sanitized_data.get("data")
            if isinstance(signal, dict):
                self.latest_signal = signal
                logger.info(f"[DEBUG] SIGNAL stored: direction={signal.get('direction')}")
        elif msg_type == "EXECUTION_ACK":
            ack = sanitized_data.get("data")
            if isinstance(ack, dict):
                self.latest_execution_ack = ack
        elif msg_type == "ENGINE_STATUS":
            engine_status = sanitized_data.get("data")
            if isinstance(engine_status, dict):
                self.latest_engine_status = engine_status
                runtime_state.set_engine_status(**engine_status)

        if not self.active_connections:
            logger.info("[DEBUG] broadcast_json: no frontend clients connected, skipping")
            return

        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(sanitized_data)
            except Exception as e:
                logger.error(f"Failed to send to frontend: {e}")
                dead.append(conn)

        for conn in dead:
            self.disconnect(conn)

    def update_tick(self, tick_data: dict):
        self.latest_tick = tick_data


manager = FrontendConnectionManager()


@router.websocket("/signals")
async def signals_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                msg_type = payload.get("type")
                
                if msg_type == "PING":
                    await websocket.send_json({"type": "PONG"})
                elif msg_type == "SUBSCRIBE":
                    logger.info(f"Frontend subscribed to: {payload.get('channels', [])}")
            except json.JSONDecodeError:
                logger.error("Failed to decode JSON from frontend")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


def relay_tick_to_frontend(tick_data: dict):
    import asyncio
    manager.latest_tick = tick_data
    asyncio.create_task(manager.broadcast_json({"type": "TICK", "data": tick_data}))


def relay_candles_to_frontend(symbol: str, timeframe: str, candles: list):
    import asyncio
    asyncio.create_task(manager.broadcast_json({
        "type": "CANDLES",
        "data": {"symbol": symbol, "timeframe": timeframe, "candles": candles}
    }))


def relay_signal_to_frontend(signal_data: dict):
    import asyncio
    asyncio.create_task(manager.broadcast_json({"type": "SIGNAL", "data": signal_data}))


def relay_signal_batch_to_frontend(batch_data: dict):
    import asyncio
    asyncio.create_task(manager.broadcast_json({"type": "SIGNAL_BATCH", "data": batch_data}))


def relay_engine_status_to_frontend(engine_status: dict):
    import asyncio
    manager.latest_engine_status = engine_status
    asyncio.create_task(manager.broadcast_json({"type": "ENGINE_STATUS", "data": engine_status}))
