from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class ExecutionAdjustment:
    session: str
    volatility_bucket: str
    current_spread: float
    typical_spread: float
    confidence_multiplier: float
    tradeable: bool
    reason: str = ""


class ExecutionModel:
    SPREAD_BY_SESSION = {
        "london": 0.35,
        "ny": 0.35,
        "asian": 0.55,
        "off": 0.70,
    }
    SPREAD_BY_VOLATILITY = {
        "low": 0.90,
        "medium": 1.00,
        "high": 1.25,
    }
    _spread_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=64))

    @classmethod
    def observe_spread(cls, symbol: str, spread: float | None) -> None:
        if spread is None or spread <= 0:
            return
        cls._spread_history[symbol].append(float(spread))

    @classmethod
    def get_session_label(cls, hour: int) -> str:
        if 8 <= hour < 12:
            return "london"
        if 13 <= hour < 17:
            return "ny"
        if 0 <= hour < 7:
            return "asian"
        return "off"

    @classmethod
    def get_volatility_bucket(cls, atr_ratio: float) -> str:
        if atr_ratio >= 1.2:
            return "high"
        if atr_ratio <= 0.85:
            return "low"
        return "medium"

    @classmethod
    def get_spread_estimate(cls, symbol: str, session: str, volatility: str) -> float:
        history = cls._spread_history.get(symbol)
        if history and len(history) >= 5:
            return float(median(history))
        base = cls.SPREAD_BY_SESSION.get(session, cls.SPREAD_BY_SESSION["off"])
        return round(base * cls.SPREAD_BY_VOLATILITY.get(volatility, 1.0), 4)

    @classmethod
    def apply_slippage_buffer(cls, entry: float, direction: str, spread: float) -> tuple[float, float]:
        half_spread = max(spread, 0.0) * 0.5
        if direction == "BUY":
            return entry + half_spread, half_spread
        if direction == "SELL":
            return entry - half_spread, half_spread
        return entry, 0.0

    @classmethod
    def is_tradeable(cls, symbol: str, regime: str, current_spread: float, typical_spread: float) -> bool:
        _ = symbol
        if regime == "transition":
            return False
        if typical_spread <= 0:
            return current_spread <= 1.0
        return current_spread <= typical_spread * 2.0

    @classmethod
    def get_confidence_penalty(cls, current_spread: float, typical_spread: float, regime: str) -> float:
        if regime == "transition":
            return 0.60
        if typical_spread <= 0:
            return 0.90
        spread_ratio = current_spread / typical_spread
        if spread_ratio >= 2.0:
            return 0.60
        if spread_ratio >= 1.5:
            return 0.78
        if spread_ratio >= 1.25:
            return 0.88
        return 1.0

    @classmethod
    def apply_execution_correction(
        cls,
        *,
        symbol: str,
        direction: str,
        regime: str,
        session: str,
        volatility_bucket: str,
        current_spread: float,
        entry_price: float,
    ) -> ExecutionAdjustment:
        typical_spread = cls.get_spread_estimate(symbol, session, volatility_bucket)
        tradeable = cls.is_tradeable(symbol, regime, current_spread, typical_spread)
        multiplier = cls.get_confidence_penalty(current_spread, typical_spread, regime)
        _, slippage_buffer = cls.apply_slippage_buffer(entry_price, direction, current_spread)
        reason = ""
        if not tradeable:
            reason = "spread_anomaly"
        elif slippage_buffer > 0:
            reason = "execution_friction"
        return ExecutionAdjustment(
            session=session,
            volatility_bucket=volatility_bucket,
            current_spread=round(current_spread, 4),
            typical_spread=round(typical_spread, 4),
            confidence_multiplier=round(multiplier, 4),
            tradeable=tradeable,
            reason=reason,
        )
