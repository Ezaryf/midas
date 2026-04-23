import unittest

from app.services.symbols import normalize_symbol, resolve_execution_symbol, symbols_match


class SymbolNormalizationTests(unittest.TestCase):
    def test_gold_aliases_normalize_to_xauusd(self):
        self.assertEqual(normalize_symbol("GOLD"), "XAUUSD")
        self.assertEqual(normalize_symbol("XAUUSDm"), "XAUUSD")
        self.assertEqual(normalize_symbol("GCQ26"), "XAUUSD")

    def test_gold_aliases_match_each_other(self):
        self.assertTrue(symbols_match("GOLD", "XAUUSD"))
        self.assertTrue(symbols_match("XAUUSDm", "XAUUSD"))
        self.assertTrue(symbols_match("GCQ26", "GOLD"))

    def test_resolve_execution_symbol_prefers_matching_broker_symbol(self):
        self.assertEqual(resolve_execution_symbol("XAUUSD", broker_symbol="GOLD"), "GOLD")
        self.assertEqual(resolve_execution_symbol("XAU/USD", tick_symbol="GOLD"), "GOLD")
        self.assertEqual(resolve_execution_symbol("EURUSD", broker_symbol="GOLD"), "EURUSD")


if __name__ == "__main__":
    unittest.main()
