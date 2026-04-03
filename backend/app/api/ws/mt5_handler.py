from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
from collections import deque

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter()


class MT5ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.latest_tick: dict | None = None
        # Buffer last 10 signals so bridge gets them on reconnect
        self._pending_signals: deque[dict] = deque(maxlen=10)
        # Track signal acknowledgments: signal_id -> {"status": "ok"|"error", "message": str}
        self._signal_acks: dict[str, dict] = {}
        # Runtime trading style — set by frontend, read by loop
        self.trading_style: str | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"MT5 local agent connected.")

        # Replay any pending signals to the newly connected bridge
        if self._pending_signals:
            logger.info(f"Replaying {len(self._pending_signals)} pending signal(s) to new connection.")
            for signal in list(self._pending_signals):
                try:
                    await websocket.send_json(signal)
                except Exception:
                    pass
            self._pending_signals.clear()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"MT5 local agent disconnected.")

    async def broadcast_json(self, data: dict):
        """Sends a JSON payload to all active connections."""
        if not self.active_connections:
            # No bridge connected — queue the signal for when it reconnects
            if data.get("type") == "SIGNAL":
                self._pending_signals.append(data)
                logger.warning("No bridge connected — signal queued for next connection.")
            return

        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(data)
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
                dead.append(conn)

        for conn in dead:
            self.disconnect(conn)

    def store_ack(self, signal_id: str, ack_data: dict):
        """Store acknowledgment from bridge for a signal execution."""
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
            self.latest_tick = data.get("data")
            await self.broadcast_json({"type": "TICK", "data": self.latest_tick})
        
        elif msg_type == "ACK":
            # Acknowledgment of signal execution
            signal_id = data.get("signal_id")
            if signal_id:
                self.store_ack(signal_id, data)
        
        elif msg_type == "PONG":
            # Heartbeat response
            pass


manager = MT5ConnectionManager()


@router.websocket("/mt5")
async def mt5_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                await manager.process_incoming_data(payload)
            except json.JSONDecodeError:
                logger.error("Failed to decode JSON from MT5 agent")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
