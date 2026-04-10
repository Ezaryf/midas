from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from app.services.database import db
from app.services.shadow_engine import ShadowEngine
from app.services.trading_state import trading_state

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:  # pragma: no cover - optional in tests
    mt5 = None


@dataclass
class SignalOutcome:
    ticket: int
    signal_id: str | None
    analysis_batch_id: str | None
    symbol: str | None
    direction: str
    setup_type: str | None
    trading_style: str | None
    intended_entry_price: float | None
    intended_stop_loss: float | None
    intended_take_profit_1: float | None
    actual_entry_price: float | None
    actual_exit_price: float | None
    actual_entry_time: datetime | None
    actual_exit_time: datetime | None
    regime_at_signal: str | None
    regime_confidence_at_signal: float | None
    session_at_signal: str | None
    volatility_bucket_at_signal: str | None
    spread_at_signal: float | None
    data_source_at_signal: str | None
    compression_ratio_at_entry: float | None
    efficiency_ratio_at_entry: float | None
    close_location_at_entry: float | None
    body_strength_at_entry: float | None
    pnl_points: float | None
    pnl_dollars: float | None
    outcome: str
    actual_spread: float | None
    slippage_points: float | None
    fill_quality: str


class SignalFeedbackStore:
    def __init__(self) -> None:
        self.shadow_engine = ShadowEngine()

    @staticmethod
    def _load_signal_context(order_row: dict[str, Any]) -> dict[str, Any]:
        raw_context = order_row.get("signal_context")
        if not raw_context:
            return {}
        if isinstance(raw_context, dict):
            return raw_context
        try:
            return json.loads(raw_context)
        except Exception:
            return {}

    @staticmethod
    def _fill_quality(slippage_points: float | None) -> str:
        if slippage_points is None:
            return "unknown"
        absolute_slippage = abs(slippage_points)
        if absolute_slippage <= 0.1:
            return "excellent"
        if absolute_slippage <= 0.25:
            return "good"
        if absolute_slippage <= 0.5:
            return "fair"
        return "poor"

    def record_outcome(self, ticket: int) -> None:
        if not db.is_enabled():
            return
        order_row = db.get_order_by_ticket(ticket)
        if not order_row or db.signal_outcome_exists(ticket):
            return

        signal_row = db.get_signal_by_id(order_row.get("signal_id")) if order_row.get("signal_id") else {}
        context = self._load_signal_context(order_row)
        actual_entry = float(order_row.get("entry_price") or 0.0)
        actual_exit = float(order_row.get("close_price") or 0.0)
        pnl_points = None
        if actual_entry and actual_exit:
            if order_row.get("direction") == "BUY":
                pnl_points = actual_exit - actual_entry
            else:
                pnl_points = actual_entry - actual_exit

        profit = float(order_row.get("profit") or 0.0)
        outcome = "breakeven"
        if profit > 0:
            outcome = "win"
        elif profit < 0:
            outcome = "loss"

        slippage_points = context.get("slippage_points")
        payload = SignalOutcome(
            ticket=ticket,
            signal_id=order_row.get("signal_id"),
            analysis_batch_id=context.get("analysis_batch_id") or signal_row.get("analysis_batch_id"),
            symbol=order_row.get("symbol") or signal_row.get("symbol"),
            direction=str(order_row.get("direction", "HOLD")),
            setup_type=context.get("setup_type") or signal_row.get("setup_type"),
            trading_style=context.get("trading_style") or signal_row.get("trading_style"),
            intended_entry_price=context.get("intended_entry_price"),
            intended_stop_loss=context.get("intended_stop_loss"),
            intended_take_profit_1=context.get("intended_take_profit_1"),
            actual_entry_price=actual_entry or None,
            actual_exit_price=actual_exit or None,
            actual_entry_time=order_row.get("created_at"),
            actual_exit_time=order_row.get("closed_at"),
            regime_at_signal=context.get("regime_at_signal") or signal_row.get("market_regime"),
            regime_confidence_at_signal=context.get("regime_confidence_at_signal"),
            session_at_signal=context.get("session_at_signal"),
            volatility_bucket_at_signal=context.get("volatility_bucket_at_signal"),
            spread_at_signal=context.get("spread_at_signal"),
            data_source_at_signal=context.get("data_source_at_signal") or signal_row.get("source"),
            compression_ratio_at_entry=context.get("compression_ratio_at_entry"),
            efficiency_ratio_at_entry=context.get("efficiency_ratio_at_entry"),
            close_location_at_entry=context.get("close_location_at_entry"),
            body_strength_at_entry=context.get("body_strength_at_entry"),
            pnl_points=pnl_points,
            pnl_dollars=profit,
            outcome=outcome,
            actual_spread=context.get("actual_spread"),
            slippage_points=slippage_points,
            fill_quality=self._fill_quality(slippage_points),
        )
        db.save_signal_outcome(asdict(payload))
        self.shadow_engine.compare_to_actual(asdict(payload))
        trading_state.record_completion(is_loss=profit < 0, loss_amount=abs(profit) if profit < 0 else 0.0)

    def sync_closed_orders(self, *, magic_number: int = 20250101) -> None:
        if mt5 is None or not db.is_enabled():
            return

        live_positions = mt5.positions_get(magic=magic_number) or []
        live_tickets = {int(position.ticket) for position in live_positions}
        open_orders = db.get_open_orders()
        if not open_orders:
            return

        now = datetime.now(timezone.utc)
        history_start = now - timedelta(days=7)
        deals = mt5.history_deals_get(history_start, now, magic=magic_number) or []

        for order in open_orders:
            ticket = int(order.get("ticket"))
            if ticket in live_tickets:
                continue

            close_deal = next(
                (
                    deal
                    for deal in reversed(deals)
                    if int(getattr(deal, "position_id", 0) or getattr(deal, "order", 0) or 0) == ticket
                    or int(getattr(deal, "order", 0) or 0) == ticket
                ),
                None,
            )
            if close_deal is None:
                continue

            close_price = float(getattr(close_deal, "price", 0.0))
            profit = float(getattr(close_deal, "profit", 0.0))
            commission = float(getattr(close_deal, "commission", 0.0))
            swap = float(getattr(close_deal, "swap", 0.0))
            reason = str(getattr(close_deal, "comment", "") or getattr(close_deal, "reason", "BROKER_CLOSE"))
            db.update_order_close(
                ticket=ticket,
                close_price=close_price,
                profit=profit,
                commission=commission,
                swap=swap,
                close_reason=reason,
            )
            self.record_outcome(ticket)


signal_feedback_store = SignalFeedbackStore()
