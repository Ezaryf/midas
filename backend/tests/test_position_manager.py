import unittest

from app.services.position_manager import (
    PositionAction,
    PositionContext,
    PositionManager,
    PositionManagerConfig,
)
from app.schemas.signal import TradeSignal


class PositionManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = PositionManager(
            PositionManagerConfig(
                enabled=True,
                cooldown_seconds=30,
                reverse_high_confidence=85.0,
                reverse_medium_confidence=70.0,
                reverse_loss_threshold_dollars=50.0,
                scale_in_confidence=90.0,
                scale_in_lot_fraction=0.5,
            )
        )

    @staticmethod
    def _position(direction: str, pnl_dollars: float) -> PositionContext:
        return PositionContext(
            ticket=123456,
            direction=direction,
            entry_price=3200.0,
            current_price=3202.0 if direction == "BUY" else 3198.0,
            pnl_points=2.0,
            pnl_dollars=pnl_dollars,
            volume=0.1,
            age_minutes=12.0,
            stop_loss=3195.0,
            take_profit=3210.0,
        )

    def test_duplicate_signal_is_suppressed_within_cooldown(self):
        self.assertFalse(self.manager.is_duplicate_signal("XAUUSD", "BUY"))
        self.assertTrue(self.manager.is_duplicate_signal("XAUUSD", "BUY"))
        self.assertFalse(self.manager.is_duplicate_signal("XAUUSD", "SELL"))

    def test_filtering_does_not_start_execution_cooldown(self):
        signal = TradeSignal(
            symbol="XAUUSD",
            direction="BUY",
            entry_price=3200.0,
            stop_loss=3198.0,
            take_profit_1=3203.0,
            take_profit_2=3205.0,
            confidence=80.0,
            reasoning="test",
            trading_style="Scalper",
        )

        filtered = self.manager.filter_signals([signal], "XAUUSD")

        self.assertFalse(filtered[0][2])
        self.assertFalse(self.manager.is_duplicate_signal("XAUUSD", "BUY", record=False))
        self.manager.mark_signal_emitted("XAUUSD", "BUY")
        self.assertTrue(self.manager.is_duplicate_signal("XAUUSD", "BUY", record=False))

    def test_same_direction_high_confidence_scales_in(self):
        decision = self.manager.decide_action(
            signal_direction="BUY",
            signal_confidence=92.0,
            position=self._position("BUY", pnl_dollars=35.0),
        )
        self.assertEqual(decision.action, PositionAction.SCALE_IN)

    def test_opposite_signal_reverses_when_profitable_or_loss_is_large(self):
        profitable_decision = self.manager.decide_action(
            signal_direction="SELL",
            signal_confidence=72.0,
            position=self._position("BUY", pnl_dollars=18.0),
        )
        loss_decision = self.manager.decide_action(
            signal_direction="SELL",
            signal_confidence=74.0,
            position=self._position("BUY", pnl_dollars=-65.0),
        )
        self.assertEqual(profitable_decision.action, PositionAction.REVERSE)
        self.assertEqual(loss_decision.action, PositionAction.REVERSE)

    def test_low_confidence_opposite_signal_is_ignored(self):
        decision = self.manager.decide_action(
            signal_direction="SELL",
            signal_confidence=65.0,
            position=self._position("BUY", pnl_dollars=-10.0),
        )
        self.assertEqual(decision.action, PositionAction.IGNORE)


if __name__ == "__main__":
    unittest.main()
