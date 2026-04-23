import unittest
from datetime import datetime, timedelta, timezone

from app.api.ws.mt5_handler import frontend_manager, manager as mt5_manager
from app.services.runtime_state import runtime_state


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


class FrontendTickCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        frontend_manager.active_connections.clear()
        frontend_manager.latest_tick = None
        frontend_manager.latest_market_state = None
        frontend_manager.latest_signal_batch = None
        frontend_manager.latest_signal = None
        frontend_manager.latest_execution_ack = None
        frontend_manager.latest_engine_status = None
        mt5_manager.latest_tick = None
        runtime_state.set_tick(None)
        runtime_state.set_engine_status(phase="booting", message="Engine starting up.")

    async def asyncTearDown(self) -> None:
        frontend_manager.active_connections.clear()
        frontend_manager.latest_tick = None
        frontend_manager.latest_market_state = None
        frontend_manager.latest_signal_batch = None
        frontend_manager.latest_signal = None
        frontend_manager.latest_execution_ack = None
        frontend_manager.latest_engine_status = None
        mt5_manager.latest_tick = None
        runtime_state.set_tick(None)
        runtime_state.set_engine_status(phase="booting", message="Engine starting up.")

    async def test_connect_replays_runtime_tick_when_frontend_cache_is_empty(self):
        tick = {
            "symbol": "GOLD",
            "bid": 4821.25,
            "ask": 4821.55,
            "time": datetime.now(timezone.utc).isoformat(),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        runtime_state.set_tick(tick)
        ws = _FakeWebSocket()

        await frontend_manager.connect(ws)

        self.assertTrue(ws.accepted)
        self.assertEqual(len(ws.sent), 2)
        self.assertEqual(ws.sent[0]["type"], "TICK")
        self.assertEqual(ws.sent[0]["data"]["symbol"], "GOLD")
        self.assertEqual(ws.sent[1]["type"], "ENGINE_STATUS")
        self.assertEqual(frontend_manager.latest_tick["symbol"], "GOLD")

    async def test_broadcast_tick_updates_frontend_cache(self):
        source_received_at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        tick = {
            "symbol": "GOLD",
            "bid": 4822.10,
            "ask": 4822.45,
            "time": datetime.now(timezone.utc).isoformat(),
            "received_at": source_received_at,
        }

        runtime_state.set_tick(tick)
        normalized_tick = runtime_state.get_tick()
        await frontend_manager.broadcast_json({"type": "TICK", "data": normalized_tick})

        self.assertEqual(frontend_manager.latest_tick["source_received_at"], source_received_at)
        self.assertNotEqual(frontend_manager.latest_tick["received_at"], source_received_at)

    async def test_mt5_tick_broadcast_uses_backend_received_at(self):
        stale_source_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        await mt5_manager.process_incoming_data(
            {
                "type": "TICK",
                "data": {
                    "symbol": "XAUUSD",
                    "bid": 4822.10,
                    "ask": 4822.45,
                    "time": stale_source_time,
                    "received_at": stale_source_time,
                    "source": "MT5",
                },
            }
        )

        self.assertEqual(frontend_manager.latest_tick["source_received_at"], stale_source_time)
        self.assertNotEqual(frontend_manager.latest_tick["received_at"], stale_source_time)
        self.assertEqual(runtime_state.get_tick()["received_at"], frontend_manager.latest_tick["received_at"])

    async def test_runtime_engine_status_is_timestamped(self):
        status = runtime_state.set_engine_status(
            phase="candidates-ranked",
            message="Candidate setups ranked.",
            detail="1 executable candidate, 2 rejected ideas.",
            symbol="XAUUSD",
            trading_style="Scalper",
            progress=65,
            candidate_count=1,
            rejected_count=2,
        )

        stored = runtime_state.get_engine_status()

        self.assertEqual(status["phase"], "candidates-ranked")
        self.assertEqual(stored["message"], "Candidate setups ranked.")
        self.assertEqual(stored["symbol"], "XAUUSD")
        self.assertEqual(stored["candidate_count"], 1)
        self.assertIn("updated_at", stored)

    async def test_broadcast_engine_status_updates_frontend_and_runtime_cache(self):
        engine_status = {
            "phase": "gates-evaluated",
            "message": "Decision gates evaluated.",
            "detail": "All blocking gates are clear.",
            "symbol": "XAUUSD",
            "trading_style": "Scalper",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "progress": 85,
        }

        await frontend_manager.broadcast_json({"type": "ENGINE_STATUS", "data": engine_status})

        self.assertEqual(frontend_manager.latest_engine_status["phase"], "gates-evaluated")
        self.assertEqual(runtime_state.get_engine_status()["phase"], "gates-evaluated")

    async def test_connect_replays_cached_analysis_state(self):
        tick = {
            "symbol": "GOLD",
            "bid": 4823.10,
            "ask": 4823.45,
            "time": datetime.now(timezone.utc).isoformat(),
            "received_at": datetime.now(timezone.utc).isoformat(),
        }
        market_state = {"symbol": "XAUUSD", "regime": "trend_up", "current_price": 4823.1}
        signal_batch = {
            "analysis_batch_id": "batch-1",
            "symbol": "XAUUSD",
            "trading_style": "Scalper",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "market_regime": "trend_up",
            "regime_summary": "Bullish continuation",
            "source": "mt5",
            "source_is_live": True,
            "primary": {
                "direction": "BUY",
                "entry_price": 4823.1,
                "stop_loss": 4820.0,
                "take_profit_1": 4828.0,
                "take_profit_2": 4832.0,
                "confidence": 71,
                "reasoning": "Momentum aligned",
                "trading_style": "Scalper",
            },
            "backups": [],
        }
        signal = {
            "signal_id": "signal-1",
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 4823.1,
            "stop_loss": 4820.0,
            "take_profit_1": 4828.0,
            "take_profit_2": 4832.0,
            "confidence": 71,
            "reasoning": "Momentum aligned",
            "trading_style": "Scalper",
        }
        ack = {"signal_id": "signal-1", "status": "ok", "symbol": "XAUUSD", "direction": "BUY", "ticket": 123}
        engine_status = {
            "phase": "analysis-complete",
            "message": "Analysis complete: BUY ready.",
            "detail": "Bullish continuation",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        runtime_state.set_tick(tick)
        await frontend_manager.broadcast_json({"type": "MARKET_STATE", "data": market_state})
        await frontend_manager.broadcast_json({"type": "SIGNAL_BATCH", "data": signal_batch})
        await frontend_manager.broadcast_json({"type": "SIGNAL", "data": signal})
        await frontend_manager.broadcast_json({"type": "EXECUTION_ACK", "data": ack})
        await frontend_manager.broadcast_json({"type": "ENGINE_STATUS", "data": engine_status})

        ws = _FakeWebSocket()
        await frontend_manager.connect(ws)

        replay_types = [payload["type"] for payload in ws.sent]
        self.assertEqual(
            replay_types,
            ["TICK", "MARKET_STATE", "SIGNAL_BATCH", "SIGNAL", "EXECUTION_ACK", "ENGINE_STATUS"],
        )


if __name__ == "__main__":
    unittest.main()
