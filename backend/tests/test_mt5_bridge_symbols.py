import importlib
import unittest
from unittest.mock import patch


try:
    mt5_bridge = importlib.import_module("mt5_bridge")
except Exception as exc:  # pragma: no cover - depends on local MT5 package availability
    mt5_bridge = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(mt5_bridge is None, f"mt5_bridge unavailable: {IMPORT_ERROR}")
class MT5BridgeSymbolTests(unittest.TestCase):
    def test_xauusd_signal_executes_with_gold_broker_symbol(self):
        def fake_symbol_info(symbol):
            return object() if symbol == "GOLD" else None

        with (
            patch.object(mt5_bridge, "SYMBOL", "GOLD"),
            patch.object(mt5_bridge.mt5, "symbol_select", return_value=True),
            patch.object(mt5_bridge.mt5, "symbol_info", side_effect=fake_symbol_info),
        ):
            symbol = mt5_bridge._resolve_order_symbol(
                {
                    "symbol": "XAUUSD",
                    "broker_symbol": "GOLD",
                    "execution_symbol": "GOLD",
                }
            )

        self.assertEqual(symbol, "GOLD")


if __name__ == "__main__":
    unittest.main()
