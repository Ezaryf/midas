import os
import unittest
from datetime import datetime, timezone

import pandas as pd

from app.core.loop import STYLE_CONFIG
from app.services.analysis_pipeline import AnalysisContext, TradingEngine
from app.services.market_state import RankedSetupBook, build_analysis_batch, build_snapshot, detect_ranked_setups


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


class ForceExecutionTests(unittest.TestCase):
    def setUp(self):
        self.previous_force = os.environ.get("FORCE_EXECUTION_MODE")
        self.previous_levels = os.environ.get("FORCE_EXECUTION_ALLOW_SYNTHETIC_LEVELS")
        os.environ["FORCE_EXECUTION_MODE"] = "true"
        os.environ["FORCE_EXECUTION_ALLOW_SYNTHETIC_LEVELS"] = "true"

    def tearDown(self):
        if self.previous_force is None:
            os.environ.pop("FORCE_EXECUTION_MODE", None)
        else:
            os.environ["FORCE_EXECUTION_MODE"] = self.previous_force
        if self.previous_levels is None:
            os.environ.pop("FORCE_EXECUTION_ALLOW_SYNTHETIC_LEVELS", None)
        else:
            os.environ["FORCE_EXECUTION_ALLOW_SYNTHETIC_LEVELS"] = self.previous_levels

    def test_force_execution_promotes_raw_candidate_when_filtered_batch_is_hold(self):
        closes = [
            100.0, 100.5, 100.2, 100.6, 100.3, 100.7, 100.4, 100.8, 100.5, 100.9,
            100.6, 101.0, 100.7, 101.1, 100.9, 101.2, 101.0, 101.3, 101.1, 101.35,
            101.2, 101.45, 101.3, 101.5, 101.4, 101.6,
        ]
        snapshots = make_snapshots(closes)
        raw_setup_book = detect_ranked_setups(
            snapshots=snapshots,
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"1m": [], "5m": []},
        )
        self.assertGreater(len(raw_setup_book.selected), 0)

        hold_batch = build_analysis_batch(
            symbol="XAUUSD",
            style="Scalper",
            snapshots=snapshots,
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"1m": [], "5m": []},
            setup_book=RankedSetupBook(selected=[], rejected=raw_setup_book.selected + raw_setup_book.rejected),
            batch_id="force-batch",
        )
        self.assertEqual(hold_batch.primary.direction, "HOLD")

        engine = TradingEngine(STYLE_CONFIG)
        context = AnalysisContext(
            symbol="XAUUSD",
            trading_style="Scalper",
            config=STYLE_CONFIG["Scalper"],
            current_price=float(snapshots["1m"].current_price),
            tick={"symbol": "XAUUSD", "bid": float(snapshots["1m"].current_price), "spread": 0.4},
            tick_symbol_match=True,
            tick_fresh=True,
            session_active=False,
            news_blocked=True,
            risk_blocked=False,
            datasets={},
            patterns_by_timeframe={"1m": [], "5m": []},
            snapshots=snapshots,
            current_price_source="live_tick",
            generated_at=datetime.now(timezone.utc),
            data_quality=None,
            effective_auto_execute_confidence=99.0,
            force_execution=True,
        )

        forced_batch = engine._promote_forced_primary(
            batch=hold_batch,
            raw_setup_book=raw_setup_book,
            context=context,
        )

        self.assertIn(forced_batch.primary.direction, {"BUY", "SELL"})
        self.assertEqual(forced_batch.primary.execution_mode, "forced")
        self.assertTrue(forced_batch.primary.forced_from_hold)
        self.assertEqual(forced_batch.primary.source_candidate_stage, "raw")

    def test_force_execution_positioning_replaces_existing_position_intent(self):
        engine = TradingEngine(STYLE_CONFIG)
        batch = build_analysis_batch(
            symbol="XAUUSD",
            style="Scalper",
            snapshots=make_snapshots([100.0] * 18 + [100.2, 100.1, 100.3, 100.2, 100.4, 101.0, 102.2, 103.4, 105.0]),
            style_cfg=STYLE_CONFIG["Scalper"],
            patterns_by_timeframe={"1m": [], "5m": []},
        )
        batch.primary.execution_mode = "forced"
        batch.primary.direction = "BUY"

        context = AnalysisContext(
            symbol="XAUUSD",
            trading_style="Scalper",
            config=STYLE_CONFIG["Scalper"],
            current_price=105.0,
            tick=None,
            tick_symbol_match=False,
            tick_fresh=False,
            session_active=False,
            news_blocked=False,
            risk_blocked=False,
            datasets={},
            patterns_by_timeframe={},
            snapshots={},
            current_price_source="test",
            generated_at=datetime.now(timezone.utc),
            force_execution=True,
        )

        original = engine.position_manager.force_action_for_signal
        try:
            engine.position_manager.force_action_for_signal = lambda symbol, direction: original(symbol, direction)  # type: ignore[method-assign]
            engine._apply_force_execution_positioning(batch=batch, context=context)
        finally:
            engine.position_manager.force_action_for_signal = original  # type: ignore[method-assign]

        self.assertIn(batch.primary.position_action, {"open", "reverse"})
        self.assertFalse(batch.primary.is_duplicate)


if __name__ == "__main__":
    unittest.main()
