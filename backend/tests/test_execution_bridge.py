import unittest
from unittest.mock import AsyncMock, patch

from app.api.ws.mt5_handler import frontend_manager, manager
from app.services.application import application_service


class ExecutionBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        manager.active_connections.clear()
        manager._pending_signals.clear()
        manager._signal_acks.clear()
        frontend_manager.active_connections.clear()
        frontend_manager.latest_execution_ack = None

    async def asyncTearDown(self) -> None:
        manager.active_connections.clear()
        manager._pending_signals.clear()
        manager._signal_acks.clear()
        frontend_manager.active_connections.clear()
        frontend_manager.latest_execution_ack = None

    async def test_execute_signal_queues_when_bridge_temporarily_disconnected(self):
        signal = {
            "direction": "BUY",
            "symbol": "XAUUSD",
            "entry_price": 4800.0,
            "stop_loss": 4795.0,
            "take_profit_1": 4810.0,
            "take_profit_2": 4820.0,
            "confidence": 75,
            "reasoning": "Manual execution test",
            "trading_style": "Scalper",
        }

        with patch("app.services.application.asyncio.sleep", new_callable=AsyncMock):
            result = await application_service.execute_signal(signal)

        self.assertEqual(result.status, "warning")
        self.assertTrue(result.data["queued"])
        self.assertEqual(result.data["pending_signals"], 1)
        queued = manager._pending_signals[0]
        self.assertEqual(queued["type"], "SIGNAL")
        self.assertEqual(queued["action"], "PLACE_ORDER")
        self.assertEqual(queued["data"]["direction"], "BUY")
        self.assertIn("signal_id", queued["data"])

    async def test_execution_ack_failure_is_cached_for_replay(self):
        ack = {
            "type": "EXECUTION_ACK",
            "data": {
                "signal_id": "sig-1",
                "status": "error",
                "message": "No tick for XAUUSD after 3 attempts",
                "symbol": "XAUUSD",
                "broker_symbol": "GOLD",
            },
        }

        await frontend_manager.broadcast_json(ack)

        self.assertEqual(frontend_manager.latest_execution_ack, ack["data"])


if __name__ == "__main__":
    unittest.main()
