import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.research.backtest_engine import run_signal_backtest
from app.schemas.signal import TradeSignal
from app.services.exchange_data import supports_exchange_symbol
from app.services.indicator_engine import compute_indicators


def make_df() -> pd.DataFrame:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100 + i for i in range(40)]
    return pd.DataFrame({
        "open": [c - 0.3 for c in closes],
        "high": [c + 0.5 for c in closes],
        "low": [c - 0.8 for c in closes],
        "close": closes,
        "volume": [1_000 + i * 5 for i in range(40)],
    }, index=[base + timedelta(minutes=i) for i in range(40)])


class ResearchStackTests(unittest.TestCase):
    def test_indicator_engine_contract(self):
        enriched = compute_indicators(make_df())
        self.assertIn("EMA_9", enriched.columns)
        self.assertIn("RSI_14", enriched.columns)
        self.assertIn("MACDh_12_26_9", enriched.columns)
        self.assertIn("ATRr_14", enriched.columns)

    def test_exchange_support_is_limited_to_crypto(self):
        self.assertTrue(supports_exchange_symbol("BTCUSD"))
        self.assertFalse(supports_exchange_symbol("XAUUSD"))

    def test_vectorbt_backtest_runs_on_signals(self):
        df = make_df()
        signals = [
            TradeSignal(
                timestamp=df.index[5].to_pydatetime(),
                direction="BUY",
                entry_price=float(df.iloc[5]["close"]),
                stop_loss=float(df.iloc[5]["close"] - 1),
                take_profit_1=float(df.iloc[5]["close"] + 2),
                take_profit_2=float(df.iloc[5]["close"] + 4),
                confidence=80,
                reasoning="test",
                trading_style="Scalper",
            ),
            TradeSignal(
                timestamp=df.index[20].to_pydatetime(),
                direction="SELL",
                entry_price=float(df.iloc[20]["close"]),
                stop_loss=float(df.iloc[20]["close"] + 1),
                take_profit_1=float(df.iloc[20]["close"] - 2),
                take_profit_2=float(df.iloc[20]["close"] - 4),
                confidence=78,
                reasoning="test",
                trading_style="Intraday",
            ),
        ]
        summary = run_signal_backtest(df, signals)
        self.assertGreaterEqual(summary.total_trades, 1)


if __name__ == "__main__":
    unittest.main()
