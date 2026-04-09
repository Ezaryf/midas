from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MarketRegime(str, Enum):
    TREND = "trend"
    RANGE = "range"
    COMPRESSION = "compression"
    TRANSITION = "transition"


REGIME_DETECTOR_MATRIX: dict[tuple[str, str], dict[str, float | bool | list[str]]] = {
    ("trend", "bullish"): {
        "allowed": ["breakout_continuation", "pullback_continuation", "demand_zone_reaction"],
        "confidence_boost": 1.15,
        "confidence_cap": 1.0,
        "force_hold": False,
        "max_position_size": 1.0,
    },
    ("trend", "bearish"): {
        "allowed": ["breakdown_retest", "lower_high_failure", "supply_zone_reaction"],
        "confidence_boost": 1.15,
        "confidence_cap": 1.0,
        "force_hold": False,
        "max_position_size": 1.0,
    },
    ("range", "neutral"): {
        "allowed": [
            "range_reversion_long",
            "range_reversion_short",
            "exhaustion_reversal_long",
            "exhaustion_reversal_short",
        ],
        "confidence_boost": 1.0,
        "confidence_cap": 0.80,
        "force_hold": False,
        "max_position_size": 1.0,
    },
    ("compression", "bullish"): {
        "allowed": ["breakout_continuation"],
        "confidence_boost": 1.0,
        "confidence_cap": 0.85,
        "force_hold": False,
        "max_position_size": 0.75,
    },
    ("compression", "bearish"): {
        "allowed": ["breakdown_retest"],
        "confidence_boost": 1.0,
        "confidence_cap": 0.85,
        "force_hold": False,
        "max_position_size": 0.75,
    },
    ("transition", "neutral"): {
        "allowed": [],
        "confidence_boost": 1.0,
        "confidence_cap": 0.50,
        "force_hold": True,
        "max_position_size": 0.25,
    },
}


@dataclass(frozen=True)
class RegimeHierarchy:
    primary: str
    secondary: str
    allowed_detectors: list[str]
    confidence_boost: float = 1.0
    confidence_cap: float = 1.0
    force_hold: bool = False
    max_position_size: float = 1.0


def _normalized_primary(regime: str, compression_ratio: float) -> str:
    if regime == "range":
        return MarketRegime.RANGE.value
    if regime == "transition":
        return MarketRegime.TRANSITION.value
    if regime == "compression" or (regime == "neutral" and compression_ratio < 0.95):
        return MarketRegime.COMPRESSION.value
    if regime.startswith("trend") or regime.startswith("breakout"):
        return MarketRegime.TREND.value
    if regime.startswith("reversal"):
        return MarketRegime.TRANSITION.value
    return MarketRegime.TRANSITION.value


def _normalized_secondary(regime: str, ema_slope: float, close_location: float) -> str:
    if regime.endswith("_up"):
        return "bullish"
    if regime.endswith("_down"):
        return "bearish"
    if ema_slope > 0 and close_location >= 0.55:
        return "bullish"
    if ema_slope < 0 and close_location <= 0.45:
        return "bearish"
    return "neutral"


def get_regime_hierarchy(regime: str, snapshot) -> RegimeHierarchy:
    primary = _normalized_primary(regime, float(getattr(snapshot, "compression_ratio", 1.0)))
    secondary = _normalized_secondary(
        regime,
        float(getattr(snapshot, "ema_slope", 0.0)),
        float(getattr(snapshot, "close_location", 0.5)),
    )

    if primary == MarketRegime.RANGE.value:
        secondary = "neutral"
    if primary == MarketRegime.TRANSITION.value:
        secondary = "neutral"

    matrix_entry = (
        REGIME_DETECTOR_MATRIX.get((primary, secondary))
        or REGIME_DETECTOR_MATRIX.get((primary, "neutral"))
        or {
            "allowed": [],
            "confidence_boost": 1.0,
            "confidence_cap": 0.75,
            "force_hold": primary == MarketRegime.TRANSITION.value,
            "max_position_size": 0.5 if primary == MarketRegime.TRANSITION.value else 1.0,
        }
    )
    return RegimeHierarchy(
        primary=primary,
        secondary=secondary,
        allowed_detectors=list(matrix_entry.get("allowed", [])),
        confidence_boost=float(matrix_entry.get("confidence_boost", 1.0)),
        confidence_cap=float(matrix_entry.get("confidence_cap", 1.0)),
        force_hold=bool(matrix_entry.get("force_hold", False)),
        max_position_size=float(matrix_entry.get("max_position_size", 1.0)),
    )


def get_allowed_detectors(hierarchy: RegimeHierarchy) -> list[str]:
    return list(hierarchy.allowed_detectors)
