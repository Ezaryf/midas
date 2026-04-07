import asyncio
import json
import logging
import random
from datetime import datetime
from typing import Optional
import websockets

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MockMT5")

class MockMT5Client:
    def __init__(self, uri="ws://localhost:8000/ws/mt5"):
        self.uri = uri
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.current_price = 4750.0

    async def connect(self):
        logger.info(f"Connecting to {self.uri}...")
        try:
            async with websockets.connect(self.uri) as websocket:
                self.ws = websocket
                logger.info("Connected successfully to Midas Engine.")
                
                # Start background tasks
                sender_task = asyncio.create_task(self.feed_simulator())
                receiver_task = asyncio.create_task(self.listen_for_commands())
                
                await asyncio.gather(sender_task, receiver_task)
                
        except websockets.ConnectionClosed:
            logger.error("Connection closed by server.")
        except Exception as e:
            logger.error(f"Connection failed: {e}")

    async def listen_for_commands(self):
        """Listens for trading commands sent from the Midas Engine."""
        try:
            while True:
                response = await self.ws.recv()
                payload = json.loads(response)
                logger.info(f"Received Command from Engine: {json.dumps(payload, indent=2)}")
                
                # Simulate executing the command
                if payload.get("action") == "PLACE_ORDER":
                    logger.warning(f"EXECUTING MT5 ORDER: {payload.get('direction')} at {payload.get('price')}")
                    
        except websockets.exceptions.ConnectionClosed:
            pass

    async def feed_simulator(self):
        """Simulates tick data from MT5 sent to the Midas Engine."""
        try:
            while True:
                # Random walk for XAU/USD price
                self.current_price += random.uniform(-0.5, 0.5)
                
                payload = {
                    "type": "TICK",
                    "data": {
                        "symbol": SYMBOL,
                        "bid":    round(self.current_price - 0.1, 2),
                        "ask":    round(self.current_price + 0.1, 2),
                        "time":   datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                }
                
                await self.ws.send(json.dumps(payload))
                await asyncio.sleep(1.0) # Tick every second
                
        except websockets.exceptions.ConnectionClosed:
            pass


if __name__ == "__main__":
    client = MockMT5Client()
    try:
        asyncio.run(client.connect())
    except KeyboardInterrupt:
        logger.info("Client stopped manually.")
