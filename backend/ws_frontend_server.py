"""
Standalone WebSocket Server for Midas Frontend
===============================================
Runs separately from FastAPI to avoid browser WebSocket issues.
Bridges frontend WebSocket connections to the backend's runtime state.

Usage:
    python ws_frontend_server.py

This creates a WebSocket server on port 8001 that:
1. Connects to backend's runtime_state for tick data
2. Broadcasts ticks/signals to all connected frontend clients
3. Runs independently of FastAPI (avoids some browser issues)

Frontend connects to: ws://127.0.0.1:8001
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Set

import websockets

# Add backend to path for imports
backend_path = Path(__file__).parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("WS-Frontend")

# Try to import from backend
try:
    from dotenv import load_dotenv
    load_dotenv(backend_path / ".env")
except ImportError:
    pass

# Import backend services
from app.services.runtime_state import runtime_state
from app.api.ws.mt5_handler import manager

PORT = int(os.getenv("WS_FRONTEND_PORT", "8001"))
BACKEND_WS_URL = os.getenv("WS_BACKEND_URL", "ws://127.0.0.1:8000/ws/mt5")

# Connected frontend clients
clients: Set[websockets.WebSocketServerProtocol] = set()


async def broadcast_to_frontend(data: dict):
    """Broadcast data to all connected frontend clients."""
    if not clients:
        return
    
    message = json.dumps(data)
    disconnected = set()
    
    for client in clients:
        try:
            await client.send(message)
        except Exception as e:
            logger.warning(f"Failed to send to client: {e}")
            disconnected.add(client)
    
    # Clean up disconnected clients
    for client in disconnected:
        clients.discard(client)


async def handle_client(websocket: websockets.WebSocketServerProtocol):
    """Handle a single frontend WebSocket connection."""
    clients.add(websocket)
    client_addr = websocket.remote_address
    logger.info(f"Frontend client connected: {client_addr}")
    
    try:
        # Send initial connection confirmation
        await websocket.send(json.dumps({
            "type": "CONNECTION",
            "data": {"status": "connected", "message": "Connected to Midas WebSocket Server"}
        }))
        
        # Keep connection alive and handle incoming messages
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f"Received from frontend: {data.get('type', 'unknown')}")
                
                # Handle different message types
                if data.get("type") == "PING":
                    await websocket.send(json.dumps({"type": "PONG"}))
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from {client_addr}")
                
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Frontend client disconnected: {client_addr}")
    except Exception as e:
        logger.error(f"Error with client {client_addr}: {e}")
    finally:
        clients.discard(websocket)


async def tick_broadcaster():
    """Background task that broadcasts tick data to frontend clients."""
    last_tick_str = ""
    
    while True:
        try:
            # Get latest tick from runtime_state
            tick = runtime_state.get_tick()
            
            if tick and tick != last_tick_str:
                last_tick_str = str(tick)
                await broadcast_to_frontend({
                    "type": "TICK",
                    "data": {
                        "symbol": tick.get("symbol", "XAUUSD"),
                        "bid": tick.get("bid"),
                        "ask": tick.get("ask"),
                        "spread": tick.get("spread"),
                        "time": tick.get("time"),
                        "source": tick.get("source", "mt5-bridge"),
                    }
                })
            
            # Check for pending signals
            if manager._pending_signals:
                pending = list(manager._pending_signals)
                if pending:
                    latest_signal = pending[-1]
                    await broadcast_to_frontend({
                        "type": "SIGNAL",
                        "data": latest_signal
                    })
            
            # Also broadcast active signal from runtime_state periodically
            # (could add more data sources here)
            
        except Exception as e:
            logger.error(f"Error in tick broadcaster: {e}")
        
        await asyncio.sleep(0.1)  # Check every 100ms for true real-time


async def main():
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("Midas Frontend WebSocket Server")
    logger.info("=" * 50)
    logger.info(f"Starting on port {PORT}")
    logger.info(f"Frontend should connect to: ws://127.0.0.1:{PORT}")
    logger.info("=" * 50)
    
    # Start background tick broadcaster
    broadcaster_task = asyncio.create_task(tick_broadcaster())
    
    # Start WebSocket server
    async with websockets.serve(handle_client, "0.0.0.0", PORT):
        logger.info(f"WebSocket server running on ws://0.0.0.0:{PORT}")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down WebSocket server...")
