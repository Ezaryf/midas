import unittest
from unittest.mock import patch

import pandas as pd

from app.research.backtest_engine import optimize_weights_walk_forward
from app.services.data_quality import filter_signals_by_data_quality, get_data_quality_context
from app.services.execution_model import ExecutionModel
from app.services.kill_switch import KillSwitch, KillSwitchContext
from app.services.market_state import RankedSetupBook, SetupCandidate
from app.services.score_calibration import ScoreCalibrator
from app.services.candle_source import CandleSourceResult


class SafetyServiceTests(unittest.TestCase):
    def test_data_quality_blocks_live_only_setup_when_primary_data_is_stale(self):
        index = pd.date_range("2026-01-01", periods=5, freq="min", tz="UTC")
        df = pd.DataFrame(
            {
                "open": [100, 100.1, 100.2, 100.3, 100.4],
                "high": [100.2, 100.3, 100.4, 100.5, 100.6],
                "low": [99.8, 99.9, 100.0, 100.1, 100.2],
                "close": [100.1, 100.2, 100.3, 100.4, 100.5],
                "volume": [10, 11, 12, 13, 14],
            },
            index=index,
        )
        source_result = CandleSourceResult(
            df=df,
            symbol="XAUUSD",
            timeframe="1m",
            lookback="1d",
            source="mt5",
            is_live=True,
            confidence_cap=98.0,
            last_candle_time=index[-1].to_pydatetime(),
            age_seconds=180.0,
            freshness_ok=False,
            max_expected_age_seconds=60.0,
            notes=["live_source"],
        )
        context = get_data_quality_context(symbol="XAUUSD", timeframe="1m", source_result=source_result)
        book = RankedSetupBook(
            selected=[
                SetupCandidate(
                    direction="BUY",
                    setup_type="micro_scalp_long",
                    market_regime="trend_up",
                    entry_price=100.5,
                    stop_loss=100.0,
                    take_profit_1=101.0,
                    take_profit_2=101.5,
                    entry_window_low=100.4,
                    entry_window_high=100.6,
                    score=80.0,
                    structure_score=80.0,
                    rr=1.5,
                    reasoning="test",
                ),
                SetupCandidate(
                    direction="BUY",
                    setup_type="demand_zone_reaction",
                    market_regime="trend_up",
                    entry_price=100.5,
                    stop_loss=100.0,
                    take_profit_1=101.0,
                    take_profit_2=101.5,
                    entry_window_low=100.4,
                    entry_window_high=100.6,
                    score=70.0,
                    structure_score=70.0,
                    rr=1.5,
                    reasoning="test",
                ),
            ],
            rejected=[],
        )

        filtered = filter_signals_by_data_quality(book, context)
        self.assertEqual(len(filtered.selected), 0)
        self.assertEqual(len(filtered.rejected), 2)
        self.assertTrue(any(reason["code"] == "data_quality_block" for reason in filtered.rejected[0].no_trade_reasons))

    def test_score_calibrator_falls_back_to_baseline_without_outcome_data(self):
        result = ScoreCalibrator.get_calibrated_confidence(
            raw_score=92.0,
            market_regime="trend_up",
            session="london",
            execution_multiplier=1.0,
            setup_type="breakout_continuation",
        )
        self.assertGreater(result.calibrated_confidence, 70.0)
        self.assertEqual(result.calibration_sample_size, 0)
        self.assertFalse(result.used_empirical_data)

    def test_execution_model_marks_spread_anomaly_as_untradeable(self):
        ExecutionModel.observe_spread("XAUUSD", 0.30)
        ExecutionModel.observe_spread("XAUUSD", 0.32)
        ExecutionModel.observe_spread("XAUUSD", 0.31)
        ExecutionModel.observe_spread("XAUUSD", 0.33)
        ExecutionModel.observe_spread("XAUUSD", 0.29)
        adjustment = ExecutionModel.apply_execution_correction(
            symbol="XAUUSD",
            direction="BUY",
            regime="trend_up",
            session="london",
            volatility_bucket="medium",
            current_spread=0.90,
            entry_price=3200.0,
        )
        self.assertFalse(adjustment.tradeable)
        self.assertEqual(adjustment.reason, "spread_anomaly")

    def test_kill_switch_prioritizes_halt_conditions(self):
        decision = KillSwitch.check(
            KillSwitchContext(
                symbol="XAUUSD",
                data_age_seconds=400.0,
                regime_stability=0.4,
                current_spread=1.0,
                typical_spread=0.3,
                drawdown_pct=20.0,
                consecutive_losses=6,
                transition_cluster=True,
            )
        )
        self.assertTrue(decision.halt_trading)
        self.assertEqual(decision.size_multiplier, 0.0)
        self.assertIn("data_staleness", decision.reasons)

    @patch("app.research.backtest_engine.db")
    def test_walk_forward_optimization_saves_results(self, mock_db):
        index = pd.date_range("2026-01-01", periods=120, freq="D", tz="UTC")
        df = pd.DataFrame({"close": range(120)}, index=index)

        results = optimize_weights_walk_forward(
            df=df,
            symbol="XAUUSD",
            trading_style="Intraday",
            timeframe="1h",
            search_space={"trend": [0.2, 0.4], "mean_reversion": [0.6, 0.8]},
            objective=lambda train_df, validate_df, weights: len(train_df) + len(validate_df) + sum(weights.values()),
            train_days=30,
            validate_days=15,
        )
        self.assertGreater(len(results), 0)
        self.assertTrue(mock_db.save_optimized_weights.called)


if __name__ == "__main__":
    unittest.main()
