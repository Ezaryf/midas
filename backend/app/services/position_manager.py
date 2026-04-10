"""
Position Manager Service
========================
Adds a position-aware decision layer to the Midas trading engine.

Responsibilities:
  - Query current open positions for a symbol
  - Deduplicate rapid-fire identical signals (cooldown per symbol:direction)
  - Decide the correct action when a new signal conflicts with an existing position:
      open / close / reverse / reduce / scale_in / ignore
  - Log every decision to the `position_decisions` database table for auditability
"""
from __future__ import annotations

import logging
import os
import threading
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Enums & Data ──────────────────────────────────────────────────────────────


class PositionAction(str, Enum):
    OPEN = "open"
    CLOSE = "close"
    REVERSE = "reverse"
    REDUCE = "reduce"
    IGNORE = "ignore"
    SCALE_IN = "scale_in"
    COUNTER_ADD = "counter_add"


@dataclass
class PositionContext:
    """Snapshot of a single open position for the symbol."""

    ticket: int
    direction: str  # "BUY" or "SELL"
    entry_price: float
    current_price: float
    pnl_points: float
    pnl_dollars: float
    volume: float
    age_minutes: float
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass
class PositionDecision:
    """Result of the position-aware decision engine."""

    action: PositionAction
    reason: str
    position: PositionContext | None = None


# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass
class PositionManagerConfig:
    enabled: bool = True
    cooldown_seconds: int = 30

    # Reversal thresholds
    reverse_high_confidence: float = 78.0
    reverse_medium_confidence: float = 62.0
    reverse_loss_threshold_dollars: float = 50.0

    # Scale-in thresholds
    scale_in_confidence: float = 82.0
    scale_in_lot_fraction: float = 0.5  # 50% of original lot

    # Counter entry thresholds (bidirectional scalping)
    counter_entry_enabled: bool = True
    counter_entry_confidence: float = 75.0
    counter_pullback_pips: float = 10.0
    counter_lot_multiplier: float = 0.5  # 50% of original lot

    @classmethod
    def from_db(cls, account_id: str = "default") -> PositionManagerConfig:
        from app.services.database import db
        db_settings = db.get_settings(account_id) if db and db.is_enabled() else {}

        def _get(key, env_key, default, type_func=float):
            if key in db_settings:
                return type_func(db_settings[key])
            return type_func(os.getenv(env_key, default))

        def _get_bool(key, env_key, default):
            if key in db_settings:
                return bool(db_settings[key])
            return os.getenv(env_key, str(default).lower()) == "true"

        return cls(
            enabled=_get_bool("enable_position_manager", "ENABLE_POSITION_MANAGER", True),
            cooldown_seconds=_get("position_cooldown_seconds", "POSITION_COOLDOWN_SECONDS", 30, int),
            reverse_high_confidence=_get("reverse_high_confidence", "REVERSE_HIGH_CONFIDENCE", 78.0, float),
            reverse_medium_confidence=_get("reverse_medium_confidence", "REVERSE_MEDIUM_CONFIDENCE", 62.0, float),
            reverse_loss_threshold_dollars=_get("reverse_loss_threshold", "REVERSE_LOSS_THRESHOLD", 50.0, float),
            scale_in_confidence=_get("scale_in_confidence", "SCALE_IN_CONFIDENCE", 82.0, float),
            scale_in_lot_fraction=_get("scale_in_lot_fraction", "SCALE_IN_LOT_FRACTION", 0.5, float),
            counter_entry_enabled=_get_bool("counter_entry_enabled", "COUNTER_ENTRY_ENABLED", True),
            counter_entry_confidence=_get("counter_entry_confidence", "COUNTER_ENTRY_CONFIDENCE", 75.0, float),
            counter_pullback_pips=_get("counter_pullback_pips", "COUNTER_PULLBACK_PIPS", 10.0, float),
            counter_lot_multiplier=_get("counter_lot_multiplier", "COUNTER_LOT_MULTIPLIER", 0.5, float),
        )

    @classmethod
    def from_env(cls, account_id: str = "default") -> PositionManagerConfig:
        return cls.from_db(account_id)


# ── Position Manager ─────────────────────────────────────────────────────────


class PositionManager:
    """
    Position-aware decision layer that sits between the scoring engine
    and the final signal output.

    It answers the question: *given this new signal and the current portfolio
    state, what is the correct action?*
    """

    def __init__(self, config: PositionManagerConfig | None = None) -> None:
        self.config = config or PositionManagerConfig.from_env()
        self._lock = threading.Lock()
        self._last_signal_time: dict[str, datetime] = {}
        self._pending_executions: dict[str, tuple[str, float, datetime]] = {}
        logger.info(
            f"PositionManager initialized: enabled={self.config.enabled} "
            f"cooldown={self.config.cooldown_seconds}s "
            f"reverse_high={self.config.reverse_high_confidence}% "
            f"scale_in={self.config.scale_in_confidence}%"
        )

    # ── Position Query ────────────────────────────────────────────────────────

    def get_current_position(self, symbol: str) -> PositionContext | None:
        """
        Retrieve the current open position for the symbol from MT5
        via the RiskManager.
        """
        try:
            from app.services.risk_manager import get_risk_manager

            risk_manager = get_risk_manager()
            if not risk_manager:
                return None

            positions = risk_manager.get_open_positions()
            if not positions:
                return None

            # Find positions matching the symbol (case-insensitive, partial match for broker variants)
            import MetaTrader5 as mt5

            for pos in positions:
                pos_symbol = getattr(pos, "symbol", "")
                if symbol.upper() not in pos_symbol.upper():
                    continue

                entry_price = float(pos.price_open)
                direction = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"

                # Compute current price from tick
                tick = mt5.symbol_info_tick(pos_symbol)
                if tick:
                    current_price = float(tick.bid) if direction == "BUY" else float(tick.ask)
                else:
                    current_price = entry_price

                pnl_points = (current_price - entry_price) if direction == "BUY" else (entry_price - current_price)

                # Age in minutes since open
                open_time = datetime.fromtimestamp(pos.time, tz=timezone.utc)
                age_minutes = (datetime.now(timezone.utc) - open_time).total_seconds() / 60.0

                return PositionContext(
                    ticket=int(pos.ticket),
                    direction=direction,
                    entry_price=round(entry_price, 2),
                    current_price=round(current_price, 2),
                    pnl_points=round(pnl_points, 2),
                    pnl_dollars=round(float(pos.profit), 2),
                    volume=round(float(pos.volume), 2),
                    age_minutes=round(age_minutes, 1),
                    stop_loss=round(float(pos.sl), 2) if pos.sl else None,
                    take_profit=round(float(pos.tp), 2) if pos.tp else None,
                )

            # If MT5 has no position, check if we literally just emitted one that hasn't executed
            if hasattr(self, "_pending_executions") and symbol in self._pending_executions:
                pending_direction, _, pending_time = self._pending_executions[symbol]
                # If less than 15 seconds passed, assume it's still being placed
                if (datetime.now(timezone.utc) - pending_time).total_seconds() < 15:
                    return PositionContext(
                        ticket=-1,
                        direction=pending_direction,
                        entry_price=0.0,
                        current_price=0.0,
                        pnl_points=0.0,
                        pnl_dollars=0.0,
                        volume=0.0,
                        age_minutes=0.0,
                    )

        except Exception as exc:
            logger.debug(f"Could not fetch position for {symbol}: {exc}")

        return None

    # ── Signal Deduplication ──────────────────────────────────────────────────

    def is_duplicate_signal(self, symbol: str, direction: str) -> bool:
        """
        Returns True if a signal with the same symbol:direction was emitted
        within the cooldown window.
        """
        key = symbol  # Block ALL signals for the symbol during cooldown to prevent whipsaws
        now = datetime.now(timezone.utc)

        with self._lock:
            last = self._last_signal_time.get(key)
            if last is not None:
                elapsed = (now - last).total_seconds()
                if elapsed < self.config.cooldown_seconds:
                    logger.info(
                        f"[PositionManager] Duplicate signal suppressed: {key} "
                        f"({elapsed:.0f}s < {self.config.cooldown_seconds}s cooldown)"
                    )
                    return True

        return False

    def mark_signal_emitted(self, symbol: str, direction: str) -> None:
        """Start the duplicate cooldown and track pending execution."""
        key = symbol
        now = datetime.now(timezone.utc)
        with self._lock:
            self._last_signal_time[key] = now
            self._pending_executions[symbol] = (direction, 0.0, now)

    def force_action_for_signal(self, symbol: str, direction: str) -> PositionDecision:
        position = self.get_current_position(symbol)
        if position is None:
            return PositionDecision(
                action=PositionAction.OPEN,
                reason="Force execution mode: no existing position, open immediately.",
            )
        return PositionDecision(
            action=PositionAction.REVERSE,
            reason=f"Force execution mode: replace existing {position.direction} position with {direction}.",
            position=position,
        )

    # ── Decision Matrix ───────────────────────────────────────────────────────

    def decide_action(
        self,
        *,
        signal_direction: str,
        signal_confidence: float,
        position: PositionContext | None,
    ) -> PositionDecision:
        """
        Core decision matrix.

        Returns:
            PositionDecision with the action and human-readable reason.
        """

        # ── No existing position ──────────────────────────────────────────────
        if position is None:
            return PositionDecision(
                action=PositionAction.OPEN,
                reason="No existing position — open new trade",
            )

        same_direction = signal_direction == position.direction
        opposite_direction = not same_direction

        # ── Same direction ────────────────────────────────────────────────────
        if same_direction:
            if signal_confidence >= self.config.scale_in_confidence:
                return PositionDecision(
                    action=PositionAction.SCALE_IN,
                    reason=(
                        f"Same direction ({position.direction}) with high confidence "
                        f"({signal_confidence:.0f}% ≥ {self.config.scale_in_confidence:.0f}%) — scale in"
                    ),
                    position=position,
                )
            return PositionDecision(
                action=PositionAction.IGNORE,
                reason=(
                    f"Same direction ({position.direction}) with moderate confidence "
                    f"({signal_confidence:.0f}% < {self.config.scale_in_confidence:.0f}%) — hold current position"
                ),
                position=position,
            )

        # ── Opposite direction ────────────────────────────────────────────────
        if opposite_direction:
            # COUNTER ENTRY: If position is in profit and we have counter entry enabled
            if (
                self.config.counter_entry_enabled
                and position.pnl_points > 0
                and signal_confidence >= self.config.counter_entry_confidence
            ):
                counter_lot = position.volume * self.config.counter_lot_multiplier
                return PositionDecision(
                    action=PositionAction.COUNTER_ADD,
                    reason=(
                        f"Counter entry: {signal_direction} @ {signal_confidence:.0f}% "
                        f"while {position.direction} position is in profit "
                        f"({position.pnl_points:.1f} pips). Adding counter position "
                        f"to complete bidirectionalscalp. "
                        f"(Counter lot: {counter_lot:.2f})"
                    ),
                    position=position,
                )

            # High confidence: always reverse
            if signal_confidence >= self.config.reverse_high_confidence:
                return PositionDecision(
                    action=PositionAction.REVERSE,
                    reason=(
                        f"Strong opposite signal ({signal_direction} @ {signal_confidence:.0f}% "
                        f"≥ {self.config.reverse_high_confidence:.0f}%) vs "
                        f"{position.direction} position — close and reverse"
                    ),
                    position=position,
                )

            # Medium confidence: reverse if profitable or in significant loss
            if signal_confidence >= self.config.reverse_medium_confidence:
                if position.pnl_dollars >= 0:
                    return PositionDecision(
                        action=PositionAction.REVERSE,
                        reason=(
                            f"Opposite signal ({signal_direction} @ {signal_confidence:.0f}%) "
                            f"and current {position.direction} position is profitable "
                            f"(${position.pnl_dollars:.2f}) — lock profit and reverse"
                        ),
                        position=position,
                    )
                if abs(position.pnl_dollars) >= self.config.reverse_loss_threshold_dollars:
                    return PositionDecision(
                        action=PositionAction.REVERSE,
                        reason=(
                            f"Opposite signal ({signal_direction} @ {signal_confidence:.0f}%) "
                            f"and current {position.direction} position has significant loss "
                            f"(${position.pnl_dollars:.2f} ≥ ${self.config.reverse_loss_threshold_dollars:.0f} threshold) "
                            f"— cut loss and reverse"
                        ),
                        position=position,
                    )

            # Low confidence opposite: ignore
            return PositionDecision(
                action=PositionAction.IGNORE,
                reason=(
                    f"Opposite signal ({signal_direction} @ {signal_confidence:.0f}%) "
                    f"is below reversal threshold — holding {position.direction} position "
                    f"(P&L: ${position.pnl_dollars:.2f})"
                ),
                position=position,
            )

        # Fallback (should not reach here)
        return PositionDecision(
            action=PositionAction.IGNORE,
            reason="Unhandled case — defaulting to IGNORE for safety",
            position=position,
        )

    # ── Signal Filtering (Pipeline Integration Point) ─────────────────────────

    def filter_signals(
        self,
        signals: list[Any],
        symbol: str,
    ) -> list[tuple[Any, PositionDecision, bool]]:
        """
        Annotate a list of TradeSignal objects with position-aware decisions.

        Returns:
            List of (signal, decision, is_duplicate) tuples.
        """
        if not self.config.enabled:
            return [
                (
                    signal,
                    PositionDecision(action=PositionAction.OPEN, reason="Position manager disabled"),
                    False,
                )
                for signal in signals
            ]

        position = self.get_current_position(symbol)
        results: list[tuple[Any, PositionDecision, bool]] = []

        for signal in signals:
            direction = getattr(signal, "direction", "HOLD")
            confidence = float(getattr(signal, "confidence", 0.0))

            # Skip non-actionable signals
            if direction not in ("BUY", "SELL"):
                results.append((
                    signal,
                    PositionDecision(action=PositionAction.IGNORE, reason="HOLD signal — no action"),
                    False,
                ))
                continue

            # Check deduplication
            is_dup = self.is_duplicate_signal(symbol, direction)

            # Decide action
            decision = self.decide_action(
                signal_direction=direction,
                signal_confidence=confidence,
                position=position,
            )

            results.append((signal, decision, is_dup))

        return results

    # ── Decision Logging ──────────────────────────────────────────────────────

    @staticmethod
    def log_decision(
        *,
        signal_id: str | None,
        symbol: str,
        signal_direction: str,
        signal_confidence: float,
        decision: PositionDecision,
        executed: bool = False,
        execution_result: str | None = None,
    ) -> None:
        """Persist a position decision to the database for audit trail."""
        from app.services.database import db

        if not db.is_enabled():
            return

        def _do_log():
            try:
                db.save_position_decision(
                    signal_id=signal_id,
                    symbol=symbol,
                    signal_direction=signal_direction,
                    signal_confidence=signal_confidence,
                    had_position=decision.position is not None,
                    position_direction=decision.position.direction if decision.position else None,
                    position_pnl_points=decision.position.pnl_points if decision.position else None,
                    position_pnl_dollars=decision.position.pnl_dollars if decision.position else None,
                    position_age_minutes=decision.position.age_minutes if decision.position else None,
                    action=decision.action.value,
                    reason=decision.reason,
                    executed=executed,
                    execution_result=execution_result,
                )
            except Exception as exc:
                logger.debug(f"Failed to log position decision: {exc}")

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _do_log)
        except RuntimeError:
            _do_log()


# ── Module-level singleton ────────────────────────────────────────────────────

_position_manager: PositionManager | None = None


def get_position_manager() -> PositionManager:
    """Get or create the global PositionManager singleton."""
    global _position_manager
    if _position_manager is None:
        _position_manager = PositionManager()
    return _position_manager
