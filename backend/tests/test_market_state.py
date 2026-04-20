import unittest
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.api.ws.mt5_handler import manager
from app.core.loop import STYLE_CONFIG, is_trading_session_active
from app.services.market_state import build_analysis_batch, build_snapshot, detect_ranked_setups, determine_market_phase
from app.services.runtime_state import runtime_state


def make_df(closes: list[float], volume_base: float = 1000) -> pd.DataFrame:
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_ = previous
        high = max(open_, close) + 0.8
        low = min(open_, close) - 0.8
        volume = volume_base + index * 5
        rows.append(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
        previous = close

    df = pd.DataFrame(rows)
    df.index = pd.date_range("2026-01-01", periods=len(df), freq="min", tz="UTC")
    df["EMA_9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["EMA_21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["EMA_50"] = df["close"].ewm(span=50, adjust=False).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    df["RSI_14"] = 100 - (100 / (1 + rs))
    ema_fast = df["close"].ewm(span=12, adjust=False).mean()
    ema_slow = df["close"].ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal = macd.ewm(span=9, adjust=False).mean()
    df["MACDh_12_26_9"] = macd - signal
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["ATRr_14"] = tr.rolling(14).mean().bfill()
    return df


def make_snapshots(primary_closes: list[float], secondary_closes: list[float] | None = None):
    secondary_closes = secondary_closes or primary_closes
    primary_df = make_df(primary_closes)
    secondary_df = make_df(secondary_closes)
    current_price = float(primary_df.iloc[-1]["close"])
    return {
        "1m": build_snapshot(primary_df, "1m", "mt5", True, current_price),
        "5m": build_snapshot(secondary_df, "5m", "mt5", True, current_price),
    }


class MarketStateEngineTests(unittest.TestCase):
    def test_detects_breakout_continuation(self):
        closes = [100.0] * 18 + [100.2, 100.1, 100.3, 100.2, 100.4, 101.0, 102.2, 103.4, 105.0]
        batch = build_analysis_batch(
            symbol="XAUUSD",
            style="Scalper",
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
        )
        self.assertEqual(batch.primary.direction, "BUY")
        self.assertEqual(batch.primary.setup_type, "breakout_continuation")

    def test_detects_pullback_continuation(self):
        # Impulse from 100 up to 105. Golden zone is 30% to 61.8% of 5, which is 1.5 to 3.09. 105 - 1.9 = 103.1.
        closes = [100.0] * 10 + [101.0, 102.0, 103.0, 104.0, 105.0, 104.6, 103.5, 103.1, 103.3]
        batch = build_analysis_batch(
            symbol="XAUUSD",
            style="Scalper",
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
        )
        self.assertEqual(batch.primary.direction, "BUY")
        self.assertIn(batch.primary.setup_type, {"pullback_continuation", "breakout_continuation"})

    def test_detects_validated_range_reversion(self):
        closes = [100, 101, 102, 103, 102, 101, 100, 99, 100, 101, 102, 103, 102, 101, 100, 99.4, 99.2]
        batch = build_analysis_batch(
            symbol="EURUSD",
            style="Intraday",
            snapshots={
                "15m": build_snapshot(make_df(closes), "15m", "mt5", True, closes[-1]),
                "1h": build_snapshot(make_df(closes), "1h", "mt5", True, closes[-1]),
            },
            style_cfg=STYLE_CONFIG["Intraday"],
            patterns_by_timeframe={"15m": [], "1h": []},
        )
        self.assertEqual(batch.primary.market_regime, "range")
        self.assertIn(batch.primary.setup_type, {"range_reversion_long", "range_reversion_short"})

    def test_detects_exhaustion_reversal(self):
        closes = [100 + i * 0.3 for i in range(16)] + [105.5, 106.2, 107.0, 107.8, 107.1]
        df = make_df(closes, volume_base=1500)
        # Force an obvious exhaustion wick on the last candle.
        df.iloc[-1, df.columns.get_loc("high")] = 109.8
        df.iloc[-1, df.columns.get_loc("close")] = 107.1
        df.iloc[-1, df.columns.get_loc("open")] = 107.9
        batch = build_analysis_batch(
            symbol="BTCUSD",
            style="Intraday",
            snapshots={
                "15m": build_snapshot(df, "15m", "mt5", True, float(df.iloc[-1]["close"])),
                "1h": build_snapshot(df, "1h", "mt5", True, float(df.iloc[-1]["close"])),
            },
            style_cfg=STYLE_CONFIG["Intraday"],
            patterns_by_timeframe={"15m": [], "1h": []},
        )
        self.assertEqual(batch.primary.direction, "SELL")
        self.assertEqual(batch.primary.setup_type, "exhaustion_reversal_short")

    def test_detects_lower_high_failure_or_breakdown(self):
        closes = [100 + i * 0.3 for i in range(10)] + [103.8, 104.2, 103.7, 103.1, 103.6, 103.0, 102.4, 101.9, 101.4]
        batch = build_analysis_batch(
            symbol="GBPUSD",
            style="Scalper",
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
        )
        self.assertEqual(batch.primary.direction, "SELL")
        self.assertIn(batch.primary.setup_type, {"lower_high_failure", "breakdown_retest", "micro_scalp_short"})

    def test_detects_micro_scalp_when_minute_rotation_is_active(self):
        closes = [
            100.0, 100.5, 100.2, 100.6, 100.3, 100.7, 100.4, 100.8, 100.5, 100.9,
            100.6, 101.0, 100.7, 101.1, 100.9, 101.2, 101.0, 101.3, 101.1, 101.35,
            101.2, 101.45, 101.3, 101.5, 101.4, 101.6,
        ]
        batch = build_analysis_batch(
            symbol="XAUUSD",
            style="Scalper",
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"1m": [], "5m": []},
        )
        self.assertIn(batch.primary.direction, {"BUY", "SELL"})
        self.assertIn(batch.primary.setup_type, {"micro_scalp_long", "pullback_continuation", "breakout_continuation"})

    def test_returns_hold_when_no_setup_survives(self):
        closes = [100.0 + (0.02 if index % 2 == 0 else -0.02) for index in range(24)]
        batch = build_analysis_batch(
            symbol="XAGUSD",
            style="Swing",
            snapshots={
                "1h": build_snapshot(make_df(closes), "1h", "mt5", True, closes[-1]),
                "4h": build_snapshot(make_df(closes), "4h", "mt5", True, closes[-1]),
            },
            style_cfg=STYLE_CONFIG["Swing"],
            patterns_by_timeframe={"1h": [], "4h": []},
        )
        self.assertEqual(batch.primary.direction, "HOLD")
        self.assertEqual(batch.primary.setup_type, "no_trade")

    def test_rejected_candidates_are_preserved_for_transparency(self):
        closes = [
            100.0, 100.5, 100.2, 100.6, 100.3, 100.7, 100.4, 100.8, 100.5, 100.9,
            100.6, 101.0, 100.7, 101.1, 100.9, 101.2, 101.0, 101.3, 101.1, 101.35,
            101.2, 101.45, 101.3, 101.5, 101.4, 101.6,
        ]
        setup_book = detect_ranked_setups(
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
        )
        self.assertGreater(len(setup_book.selected), 0)
        self.assertGreater(len(setup_book.rejected), 0)
        self.assertEqual(setup_book.rejected[0].no_trade_reasons[0]["code"], "directional_conflict")

        batch = build_analysis_batch(
            symbol="XAUUSD",
            style="Scalper",
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
            setup_book=setup_book,
        )
        self.assertIn(batch.primary.direction, {"BUY", "SELL"})

    def test_market_phase_tracks_backend_state_machine(self):
        snapshot = make_snapshots(
            [100.0] * 18 + [100.2, 100.1, 100.3, 100.2, 100.4, 101.0, 102.2, 103.4, 104.0]
        )["1m"]
        phase_key, phase_label, phase_description = determine_market_phase(snapshot)
        self.assertEqual(phase_key, "continuation")
        self.assertEqual(phase_label, "Continuation")
        self.assertIn("momentum", phase_description.lower())

    def test_smoothed_regime_marks_transition_when_recent_bars_disagree(self):
        closes = [
            100.0, 101.07412225984406, 101.91301595827177, 100.6759479972412, 98.4980189639795,
            100.81494838058738, 102.35621152244937, 102.60256117941196, 102.80944943933687,
            104.56591277099378, 104.33246115910487, 103.81101338270871, 103.004359107184,
            101.79420456954286, 99.41624708366838, 100.14844130366886, 99.7318607151609,
            100.08487887304952, 97.89648702706712, 97.1712042454986, 95.36262481527409,
            93.48826989170153, 92.28383473628068, 93.92850664120647, 93.41749320653084,
            92.92290396613534, 93.48512858110003, 92.15277684757928, 89.69016271278994,
            89.83367141222351, 89.83816951000964,
        ]
        snapshot = build_snapshot(make_df(closes), "1m", "mt5", True, closes[-1])
        self.assertEqual(snapshot.regime, "transition")
        self.assertLessEqual(snapshot.regime_stability, 0.67)
        self.assertEqual(len(snapshot.regime_history), 3)

    def test_allowed_detectors_filter_candidates_by_regime(self):
        closes = [100.0] * 18 + [100.2, 100.1, 100.3, 100.2, 100.4, 101.0, 102.2, 103.4, 105.0]
        setup_book = detect_ranked_setups(
            snapshots=make_snapshots(closes),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"5m": [], "1m": []},
            allowed_detectors=["range_reversion_long", "range_reversion_short"],
        )
        self.assertEqual(len(setup_book.selected), 0)
        self.assertGreater(len(setup_book.rejected), 0)
        self.assertEqual(setup_book.rejected[0].no_trade_reasons[0]["code"], "regime_gating_block")

    def test_scalper_session_can_run_with_fresh_live_tick(self):
        previous_tick = manager.latest_tick
        try:
            manager.latest_tick = {
                "symbol": "XAUUSD",
                "bid": 3125.5,
                "ask": 3125.8,
                "time": (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat(),
            }
            self.assertTrue(is_trading_session_active(style="Scalper", symbol="XAUUSD"))
        finally:
            manager.latest_tick = previous_tick

    def test_scalper_session_prefers_received_at_over_stale_broker_time(self):
        previous_tick = manager.latest_tick
        previous_runtime_tick = runtime_state.get_tick()
        try:
            runtime_state.set_tick(None)
            manager.latest_tick = {
                "symbol": "XAUUSD",
                "bid": 3125.5,
                "ask": 3125.8,
                "time": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
                "received_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            }
            self.assertTrue(is_trading_session_active(style="Scalper", symbol="XAUUSD"))
        finally:
            manager.latest_tick = previous_tick
            runtime_state.set_tick(previous_runtime_tick)

    def test_scalper_session_treats_gold_and_xauusd_as_same_symbol(self):
        previous_tick = manager.latest_tick
        previous_runtime_tick = runtime_state.get_tick()
        try:
            runtime_state.set_tick(None)
            manager.latest_tick = {
                "symbol": "GOLD",
                "bid": 3125.5,
                "ask": 3125.8,
                "received_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            }
            self.assertTrue(is_trading_session_active(style="Scalper", symbol="XAUUSD"))
        finally:
            manager.latest_tick = previous_tick
            runtime_state.set_tick(previous_runtime_tick)


if __name__ == "__main__":
    unittest.main()
