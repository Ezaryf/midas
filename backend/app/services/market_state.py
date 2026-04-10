"""
Sequence-aware market-state engine for ranked trade setup generation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

import pandas as pd

from app.schemas.signal import AnalysisBatch, TradeSignal

logger = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    timeframe: str
    source: str
    is_live: bool
    current_price: float
    atr: float
    avg_body: float
    body_strength: float
    upper_wick: float
    lower_wick: float
    close_location: float
    relative_volume: float
    efficiency_ratio: float
    compression_ratio: float
    ema_slope: float
    range_high: float
    range_low: float
    range_width: float
    boundary_touches_high: int
    boundary_touches_low: int
    recent_high: float
    recent_low: float
    support: float
    resistance: float
    recent_minor_high: float
    prior_minor_high: float
    recent_minor_low: float
    prior_minor_low: float
    swings: list[dict]
    regime: str
    regime_confidence: float
    regime_stability: float
    regime_history: list[str]
    notes: list[str] = field(default_factory=list)


@dataclass
class SetupCandidate:
    direction: str
    setup_type: str
    market_regime: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    entry_window_low: float
    entry_window_high: float
    score: float
    structure_score: float
    rr: float
    reasoning: str
    context_tags: list[str] = field(default_factory=list)
    source: str = "unknown"
    evidence: dict[str, float] = field(default_factory=dict)
    no_trade_reasons: list[dict[str, str | bool]] = field(default_factory=list)
    is_rejected: bool = False


@dataclass
class RankedSetupBook:
    selected: list[SetupCandidate] = field(default_factory=list)
    rejected: list[SetupCandidate] = field(default_factory=list)


PHASE_DETAILS: dict[str, tuple[str, str]] = {
    "compression": ("Compression", "Volatility is compressing and the engine is waiting for expansion."),
    "breakout": ("Breakout", "Price is leaving a defined box and momentum confirmation is active."),
    "impulse": ("Impulse", "Directional flow is strong and the market is extending away from balance."),
    "pullback": ("Pullback", "Trend is intact, but price is retracing into a continuation zone."),
    "continuation": ("Continuation", "Structure and momentum still support the active directional move."),
    "weakening": ("Weakening", "Trend strength is fading and reversal or failure signals are building."),
    "range": ("Range", "Auction is rotating between support and resistance with mean-reversion behavior."),
}


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den not in (0, 0.0) else default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _round_price(price: float) -> float:
    return round(float(price), 2)


def _recent_slice(df: pd.DataFrame, size: int) -> pd.DataFrame:
    return df.iloc[-size:] if len(df) > size else df


def _find_swings(df: pd.DataFrame, window: int = 3) -> list[dict]:
    swings: list[dict] = []
    if len(df) < (window * 2 + 1):
        return swings

    for i in range(window, len(df) - window):
        high = df.iloc[i]["high"]
        low = df.iloc[i]["low"]
        surrounding = df.iloc[i - window : i + window + 1]
        if high == surrounding["high"].max():
            swings.append({"type": "high", "index": i, "price": float(high)})
        if low == surrounding["low"].min():
            swings.append({"type": "low", "index": i, "price": float(low)})
    return swings


def _count_touches(series: pd.Series, level: float, tolerance: float) -> int:
    if series.empty:
        return 0
    return int(((series - level).abs() <= tolerance).sum())


def _efficiency_ratio(close: pd.Series, length: int = 14) -> float:
    window = close.tail(length + 1)
    if len(window) < 2:
        return 0.0
    net_change = abs(float(window.iloc[-1] - window.iloc[0]))
    travel = float(window.diff().abs().sum())
    return _safe_div(net_change, travel, 0.0)


def _relative_volume(volume: pd.Series, lookback: int = 20) -> float:
    window = volume.tail(lookback + 1)
    if window.empty:
        return 1.0
    baseline = float(window.iloc[:-1].mean()) if len(window) > 1 else float(window.iloc[-1])
    current = float(window.iloc[-1])
    if baseline <= 0:
        return 1.0
    return current / baseline


def _classify_regime_state(recent: pd.DataFrame) -> tuple[str, float]:
    if recent.empty:
        return "transition", 35.0

    recent = recent.copy()
    box = recent.iloc[:-1] if len(recent) > 10 else recent
    last = recent.iloc[-1]
    atr = float(last.get("ATRr_14", recent["high"].sub(recent["low"]).tail(14).mean()))
    atr = max(atr, 0.01)
    body = abs(float(last["close"] - last["open"]))
    avg_body = float(recent["close"].sub(recent["open"]).abs().tail(14).mean()) or atr * 0.25
    total_range = max(float(last["high"] - last["low"]), 0.01)
    upper_wick = float(last["high"] - max(last["open"], last["close"]))
    lower_wick = float(min(last["open"], last["close"]) - last["low"])
    close_location = _safe_div(float(last["close"] - last["low"]), total_range, 0.5)

    atr_series = recent.get("ATRr_14", recent["high"].sub(recent["low"]))
    recent_atr = float(atr_series.tail(8).mean())
    prior_atr = float(atr_series.tail(24).head(16).mean()) if len(atr_series) >= 24 else recent_atr
    compression_ratio = _safe_div(recent_atr, prior_atr or recent_atr, 1.0)

    ema_slope = float(last.get("EMA_9", last["close"]) - recent.iloc[-5].get("EMA_9", recent.iloc[-5]["close"])) if len(recent) >= 5 else 0.0
    range_high = float(box["high"].tail(20).max())
    range_low = float(box["low"].tail(20).min())
    range_width = max(range_high - range_low, atr)
    efficiency = _efficiency_ratio(recent["close"], 14)
    recent_high = float(recent["high"].tail(10).max())
    recent_low = float(recent["low"].tail(10).min())
    body_strength = _safe_div(body, avg_body or body, 1.0)

    regime = "neutral"
    regime_confidence = 35.0
    if range_width < (atr * 4.0) and efficiency < 0.5:
        regime = "range"
        regime_confidence = 72.0
    elif float(last["close"]) > range_high and body_strength >= 1.2 and close_location > 0.6:
        regime = "breakout_up"
        regime_confidence = 78.0
    elif float(last["close"]) < range_low and body_strength >= 1.2 and close_location < 0.4:
        regime = "breakout_down"
        regime_confidence = 78.0
    elif ema_slope > atr * 0.15 and efficiency > 0.55:
        regime = "trend_up"
        regime_confidence = 66.0
    elif ema_slope < -atr * 0.15 and efficiency > 0.55:
        regime = "trend_down"
        regime_confidence = 66.0

    if regime != "range" and upper_wick > body * 1.8 and float(last["high"]) >= recent_high - atr * 0.1:
        regime = "reversal_down"
        regime_confidence = max(regime_confidence, 70.0)
    elif regime != "range" and lower_wick > body * 1.8 and float(last["low"]) <= recent_low + atr * 0.1:
        regime = "reversal_up"
        regime_confidence = max(regime_confidence, 70.0)

    if regime == "neutral" and compression_ratio < 0.9:
        regime = "compression"
        regime_confidence = 60.0

    return regime, regime_confidence


def _regime_direction(regime: str) -> str:
    if regime.endswith("_up"):
        return "bullish"
    if regime.endswith("_down"):
        return "bearish"
    return "neutral"


def _regime_primary(regime: str) -> str:
    if regime == "range":
        return "range"
    if regime == "compression":
        return "compression"
    if regime.startswith("trend") or regime.startswith("breakout"):
        return "trend"
    if regime.startswith("reversal"):
        return "transition"
    if regime == "transition":
        return "transition"
    return "compression" if regime == "neutral" else "transition"


def determine_regime_smoothed(recent: pd.DataFrame) -> tuple[str, float, float, list[str]]:
    if recent.empty:
        return "transition", 35.0, 0.0, []

    history: list[str] = []
    confidences: list[float] = []
    max_points = min(3, len(recent))
    for offset in range(max_points, 0, -1):
        truncated = recent.iloc[: len(recent) - offset + 1]
        regime, confidence = _classify_regime_state(truncated)
        history.append(regime)
        confidences.append(confidence)

    if not history:
        return "transition", 35.0, 0.0, []

    primary_counts: dict[str, int] = {}
    for regime in history:
        primary = _regime_primary(regime)
        primary_counts[primary] = primary_counts.get(primary, 0) + 1

    dominant_primary, dominant_count = max(primary_counts.items(), key=lambda item: item[1])
    regime_stability = round(dominant_count / len(history), 2)

    directions = [_regime_direction(regime) for regime in history]
    alternating_bias = (
        len(directions) == 3
        and directions[0] in {"bullish", "bearish"}
        and directions[1] in {"bullish", "bearish"}
        and directions[2] in {"bullish", "bearish"}
        and directions[0] != directions[1]
        and directions[1] != directions[2]
    )
    if dominant_count < 2 or alternating_bias:
        return "transition", round(sum(confidences) / len(confidences), 1), regime_stability, history

    if dominant_primary == "trend":
        bullish = sum(1 for direction in directions if direction == "bullish")
        bearish = sum(1 for direction in directions if direction == "bearish")
        if bullish > bearish:
            smoothed_regime = "trend_up"
        elif bearish > bullish:
            smoothed_regime = "trend_down"
        else:
            smoothed_regime = history[-1]
    elif dominant_primary == "range":
        smoothed_regime = "range"
    elif dominant_primary == "compression":
        smoothed_regime = "compression"
    else:
        smoothed_regime = "transition"

    return smoothed_regime, round(sum(confidences) / len(confidences), 1), regime_stability, history


def build_snapshot(df: pd.DataFrame, timeframe: str, source: str, is_live: bool, current_price: float) -> MarketSnapshot:
    recent = _recent_slice(df, 40).copy()
    box = recent.iloc[:-1] if len(recent) > 10 else recent
    last = recent.iloc[-1]
    atr = float(last.get("ATRr_14", recent["high"].sub(recent["low"]).tail(14).mean()))
    atr = max(atr, 0.01)
    body = abs(float(last["close"] - last["open"]))
    avg_body = float(recent["close"].sub(recent["open"]).abs().tail(14).mean()) or atr * 0.25
    total_range = max(float(last["high"] - last["low"]), 0.01)
    upper_wick = float(last["high"] - max(last["open"], last["close"]))
    lower_wick = float(min(last["open"], last["close"]) - last["low"])
    close_location = _safe_div(float(last["close"] - last["low"]), total_range, 0.5)

    atr_series = recent.get("ATRr_14", recent["high"].sub(recent["low"]))
    recent_atr = float(atr_series.tail(8).mean())
    prior_atr = float(atr_series.tail(24).head(16).mean()) if len(atr_series) >= 24 else recent_atr
    compression_ratio = _safe_div(recent_atr, prior_atr or recent_atr, 1.0)

    ema_slope = float(last.get("EMA_9", last["close"]) - recent.iloc[-5].get("EMA_9", recent.iloc[-5]["close"])) if len(recent) >= 5 else 0.0
    range_high = float(box["high"].tail(20).max())
    range_low = float(box["low"].tail(20).min())
    range_width = max(range_high - range_low, atr)
    tolerance = max(atr * 0.2, range_width * 0.04)
    touches_high = _count_touches(box["high"].tail(20), range_high, tolerance)
    touches_low = _count_touches(box["low"].tail(20), range_low, tolerance)
    swings = _find_swings(recent)
    recent_high = float(recent["high"].tail(10).max())
    recent_low = float(recent["low"].tail(10).min())
    recent_minor_high = float(recent["high"].tail(4).max())
    recent_minor_low = float(recent["low"].tail(4).min())
    prior_minor_high = (
        float(recent["high"].iloc[-10:-4].max()) if len(recent) >= 10 else recent_high
    )
    prior_minor_low = (
        float(recent["low"].iloc[-10:-4].min()) if len(recent) >= 10 else recent_low
    )
    support = range_low
    resistance = range_high
    efficiency = _efficiency_ratio(recent["close"], 14)
    rel_volume = _relative_volume(recent["volume"], 20)
    body_strength = _safe_div(body, avg_body or body, 1.0)

    regime, base_regime_confidence = _classify_regime_state(recent)
    regime, smoothed_confidence, regime_stability, regime_history = determine_regime_smoothed(recent)
    regime_confidence = round(max(base_regime_confidence, smoothed_confidence) * max(regime_stability, 0.5), 1)

    notes: list[str] = []
    if not is_live:
        notes.append("delayed_source")
    if compression_ratio < 0.9:
        notes.append("compression")
    if rel_volume > 1.25:
        notes.append("volume_expansion")
    if regime == "transition":
        notes.append("regime_transition")

    return MarketSnapshot(
        timeframe=timeframe,
        source=source,
        is_live=is_live,
        current_price=current_price,
        atr=atr,
        avg_body=avg_body,
        body_strength=body_strength,
        upper_wick=upper_wick,
        lower_wick=lower_wick,
        close_location=close_location,
        relative_volume=rel_volume,
        efficiency_ratio=efficiency,
        compression_ratio=compression_ratio,
        ema_slope=ema_slope,
        range_high=range_high,
        range_low=range_low,
        range_width=range_width,
        boundary_touches_high=touches_high,
        boundary_touches_low=touches_low,
        recent_high=recent_high,
        recent_low=recent_low,
        support=support,
        resistance=resistance,
        recent_minor_high=recent_minor_high,
        prior_minor_high=prior_minor_high,
        recent_minor_low=recent_minor_low,
        prior_minor_low=prior_minor_low,
        swings=swings,
        regime=regime,
        regime_confidence=regime_confidence,
        regime_stability=regime_stability,
        regime_history=regime_history,
        notes=notes,
    )


def determine_market_phase(snapshot: MarketSnapshot) -> tuple[str, str, str]:
    if snapshot.regime == "range":
        key = "range"
    elif snapshot.regime == "compression":
        key = "compression"
    elif snapshot.regime == "transition":
        key = "weakening"
    elif snapshot.regime.startswith("breakout"):
        key = "breakout"
    elif snapshot.regime.startswith("reversal"):
        key = "weakening"
    elif snapshot.compression_ratio < 0.9 and snapshot.regime == "neutral":
        key = "compression"
    elif snapshot.regime.startswith("trend") and snapshot.efficiency_ratio > 0.65 and snapshot.body_strength >= 1.0:
        key = "continuation"
    elif snapshot.regime.startswith("trend") and snapshot.efficiency_ratio > 0.55:
        key = "impulse"
    elif snapshot.regime.startswith("trend"):
        key = "pullback"
    elif snapshot.recent_minor_high < snapshot.prior_minor_high and snapshot.ema_slope < 0:
        key = "weakening"
    else:
        key = "compression"
    label, description = PHASE_DETAILS[key]
    return key, label, description


def _pattern_adjustments(candidate: SetupCandidate, patterns: Iterable, atr: float) -> tuple[float, list[str]]:
    adjustment = 0.0
    tags: list[str] = []
    for pattern in patterns:
        direction = getattr(pattern, "direction", "")
        entry = float(getattr(pattern, "entry_price", candidate.entry_price))
        confidence = float(getattr(pattern, "confidence", 0.0))
        tag = str(getattr(getattr(pattern, "type", None), "value", getattr(pattern, "type", "pattern")))
        if abs(entry - candidate.entry_price) > atr * 1.2:
            continue
        if direction == candidate.direction:
            adjustment += min(8.0, confidence / 18.0)
            tags.append(tag)
        elif direction in ("BUY", "SELL"):
            adjustment -= min(6.0, confidence / 22.0)
            tags.append(f"conflict:{tag}")
    return adjustment, tags


def _score_candidate(
    *,
    snapshot: MarketSnapshot,
    secondary: Optional[MarketSnapshot],
    entry_price: float,
    stop_loss: float,
    take_profit_1: float,
    structure_score: float,
    style_rr_target: float,
    direction: str,
    pattern_boost: float,
) -> tuple[float, float, dict[str, float]]:
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit_1 - entry_price)
    rr = _safe_div(reward, risk, 0.0)
    proximity = 1.0 - min(abs(snapshot.current_price - entry_price) / max(snapshot.atr, 0.01), 2.0) / 2.0
    invalidation_quality = _clamp(risk / max(snapshot.atr, 0.01), 0.25, 1.75)
    invalidation_score = 12.0 - abs(invalidation_quality - 0.9) * 8.0
    confluence = 0.0
    source_quality = 1.0 if snapshot.is_live else 0.72
    if secondary:
        if direction == "BUY" and secondary.regime in {"trend_up", "breakout_up", "reversal_up"}:
            confluence += 8.0
        elif direction == "SELL" and secondary.regime in {"trend_down", "breakout_down", "reversal_down"}:
            confluence += 8.0
        elif secondary.regime == "range":
            confluence += 3.0

    score = (
        snapshot.regime_confidence * 0.34
        + structure_score * 0.28
        + min(rr / max(style_rr_target, 1.0), 1.4) * 18.0
        + proximity * 14.0
        + max(invalidation_score, 0.0)
        + confluence
        + pattern_boost
    )
    if not snapshot.is_live:
        score -= 8.0
    evidence = {
        "regime_alignment": round(snapshot.regime_confidence, 2),
        "structure_confirmation": round(structure_score, 2),
        "actionability": round(proximity * 100, 2),
        "confluence": round(confluence, 2),
        "invalidation_quality": round(max(invalidation_score, 0.0), 2),
        "source_quality": round(source_quality * 100, 2),
        "conflict_penalty": 0.0,
        "pattern_boost": round(pattern_boost, 2),
        "rr": round(rr, 4),
        "proximity": round(proximity, 4),
    }
    return _clamp(score, 0.0, 99.0), rr, evidence


def _build_candidate(
    *,
    snapshot: MarketSnapshot,
    secondary: Optional[MarketSnapshot],
    style_cfg: dict,
    direction: str,
    setup_type: str,
    regime: str,
    entry_price: float,
    stop_loss: float,
    structure_target: float,
    structure_score: float,
    reasoning: str,
    patterns: Iterable,
    context_tags: list[str],
) -> Optional[SetupCandidate]:
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return None
    sign = 1 if direction == "BUY" else -1
    tp1 = entry_price + risk * style_cfg["rr_min"] * sign
    tp2 = entry_price + risk * style_cfg["rr_target"] * sign

    if direction == "BUY":
        tp1 = max(tp1, structure_target)
        tp2 = max(tp2, tp1 + snapshot.atr * 0.5)
    else:
        tp1 = min(tp1, structure_target)
        tp2 = min(tp2, tp1 - snapshot.atr * 0.5)

    pattern_boost, pattern_tags = _pattern_adjustments(
        SetupCandidate(
            direction=direction,
            setup_type=setup_type,
            market_regime=regime,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            entry_window_low=entry_price,
            entry_window_high=entry_price,
            score=0.0,
            structure_score=structure_score,
            rr=0.0,
            reasoning=reasoning,
        ),
        patterns,
        snapshot.atr,
    )
    score, rr, evidence = _score_candidate(
        snapshot=snapshot,
        secondary=secondary,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit_1=tp1,
        structure_score=structure_score,
        style_rr_target=style_cfg["rr_target"],
        direction=direction,
        pattern_boost=pattern_boost,
    )

    window_half = snapshot.atr * style_cfg.get("entry_window_atr", 0.18)
    candidate = SetupCandidate(
        direction=direction,
        setup_type=setup_type,
        market_regime=regime,
        entry_price=_round_price(entry_price),
        stop_loss=_round_price(stop_loss),
        take_profit_1=_round_price(tp1),
        take_profit_2=_round_price(tp2),
        entry_window_low=_round_price(entry_price - window_half),
        entry_window_high=_round_price(entry_price + window_half),
        score=score,
        structure_score=structure_score,
        rr=rr,
        reasoning=reasoning,
        context_tags=context_tags + pattern_tags,
        source=snapshot.source,
        evidence=evidence,
    )
    if rr + 1e-6 < style_cfg["rr_min"]:
        candidate.is_rejected = True
        candidate.no_trade_reasons.append(
            {
                "code": "rr_below_min",
                "message": f"Risk/reward {rr:.2f} is below the minimum threshold of {style_cfg['rr_min']:.2f}.",
                "blocking": True,
            }
        )
    return candidate


def _latest_swing(swings: list[dict], swing_type: str, skip_last: int = 0) -> Optional[dict]:
    filtered = [s for s in swings if s["type"] == swing_type]
    if len(filtered) <= skip_last:
        return None
    return filtered[-(skip_last + 1)]


def _detect_breakout(snapshot: MarketSnapshot, secondary: Optional[MarketSnapshot], style_cfg: dict, patterns: Iterable) -> list[SetupCandidate]:
    candidates: list[SetupCandidate] = []
    breakout_buffer = snapshot.atr * 0.12
    stop_buffer = snapshot.atr * style_cfg.get("stop_buffer_atr", 0.35)

    if (
        snapshot.regime in {"breakout_up", "trend_up"}
        and snapshot.current_price > snapshot.resistance
        and snapshot.body_strength >= 1.1
    ):
        entry = max(snapshot.current_price, snapshot.resistance + breakout_buffer)
        stop = snapshot.resistance - stop_buffer
        target = snapshot.recent_high + snapshot.atr * 0.8
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="BUY",
            setup_type="breakout_continuation",
            regime=snapshot.regime,
            entry_price=entry,
            stop_loss=stop,
            structure_target=target,
            structure_score=84.0,
            reasoning="Compression broke higher with a strong close outside resistance and expansion in participation.",
            patterns=patterns,
            context_tags=["breakout", "momentum", "expansion"],
        )
        if candidate:
            candidates.append(candidate)

    if (
        snapshot.regime in {"breakout_down", "trend_down", "reversal_down"}
        and snapshot.current_price < snapshot.support
        and snapshot.body_strength >= 1.1
    ):
        entry = min(snapshot.current_price, snapshot.support - breakout_buffer)
        stop = snapshot.support + stop_buffer
        target = snapshot.recent_low - snapshot.atr * 0.8
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="SELL",
            setup_type="breakdown_retest",
            regime=snapshot.regime,
            entry_price=entry,
            stop_loss=stop,
            structure_target=target,
            structure_score=84.0,
            reasoning="Support gave way with a decisive close and sellers are controlling the post-break auction.",
            patterns=patterns,
            context_tags=["breakdown", "momentum", "trend_flip"],
        )
        if candidate:
            candidates.append(candidate)

    return candidates


def _detect_pullback(snapshot: MarketSnapshot, secondary: Optional[MarketSnapshot], style_cfg: dict, patterns: Iterable) -> list[SetupCandidate]:
    candidates: list[SetupCandidate] = []
    swing_low = _latest_swing(snapshot.swings, "low", skip_last=1)
    swing_high = _latest_swing(snapshot.swings, "high")
    last_close = snapshot.current_price
    impulse_floor = swing_low["price"] if swing_low else max(snapshot.recent_low, snapshot.support)
    impulse_ceiling = swing_high["price"] if swing_high else snapshot.recent_high
    impulse = impulse_ceiling - impulse_floor
    retracement = _safe_div(impulse_ceiling - last_close, max(impulse, snapshot.atr), 0.0)
    controlled_wick = snapshot.upper_wick < max(snapshot.avg_body * 1.8, snapshot.atr * 0.5)

    if (
        snapshot.ema_slope > 0
        and snapshot.regime not in {"reversal_down", "breakout_down"}
        and controlled_wick
        and 0.30 <= retracement <= 0.618
        and last_close > max(snapshot.support, impulse_floor)
    ):
        pullback_floor = max(impulse_ceiling - impulse * 0.618, impulse_floor)
        stop = pullback_floor - snapshot.atr * style_cfg.get("stop_buffer_atr", 0.35)
        target = impulse_ceiling + snapshot.atr
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="BUY",
            setup_type="pullback_continuation",
            regime="trend_up",
            entry_price=last_close,
            stop_loss=stop,
            structure_target=target,
            structure_score=82.0,
            reasoning="The move is retracing a healthy portion of the impulse while still holding higher-low structure.",
            patterns=patterns,
            context_tags=["pullback", "higher_low", "continuation"],
        )
        if candidate:
            candidates.append(candidate)

    previous_high = _latest_swing(snapshot.swings, "high", skip_last=1)
    current_high = _latest_swing(snapshot.swings, "high")
    latest_low = _latest_swing(snapshot.swings, "low")
    failed_push_high = current_high["price"] if current_high else snapshot.recent_minor_high
    prior_push_high = previous_high["price"] if previous_high else snapshot.prior_minor_high
    structure_floor = latest_low["price"] if latest_low else snapshot.recent_minor_low
    lower_high = prior_push_high - failed_push_high
    structure_break = last_close <= structure_floor + snapshot.atr * 0.1
    if snapshot.ema_slope < 0 and lower_high > snapshot.atr * 0.18 and structure_break:
        entry = min(last_close, structure_floor)
        stop = failed_push_high + snapshot.atr * style_cfg.get("stop_buffer_atr", 0.3)
        target = snapshot.support - snapshot.atr * 0.6
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="SELL",
            setup_type="lower_high_failure",
            regime="reversal_down",
            entry_price=entry,
            stop_loss=stop,
            structure_target=target,
            structure_score=82.0,
            reasoning="The latest rally failed beneath the prior swing high and structure has started to break lower.",
            patterns=patterns,
            context_tags=["lower_high", "structure_break", "seller_absorption"],
        )
        if candidate:
            candidates.append(candidate)
    if snapshot.ema_slope < 0 and (
        last_close <= snapshot.support + snapshot.atr * 0.08
        or last_close <= snapshot.resistance - snapshot.atr * 0.9
    ):
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="SELL",
            setup_type="breakdown_retest",
            regime="trend_down",
            entry_price=last_close,
            stop_loss=max(snapshot.resistance, last_close) + snapshot.atr * style_cfg.get("stop_buffer_atr", 0.3),
            structure_target=snapshot.recent_low - snapshot.atr * 0.6,
            structure_score=78.0,
            reasoning="Price is breaking beneath local support with a failed rebound, favoring a continuation short.",
            patterns=patterns,
            context_tags=["breakdown", "failed_retest", "trend_continuation"],
        )
        if candidate:
            candidates.append(candidate)

    return candidates


def _detect_range(snapshot: MarketSnapshot, secondary: Optional[MarketSnapshot], style_cfg: dict, patterns: Iterable) -> list[SetupCandidate]:
    candidates: list[SetupCandidate] = []
    if snapshot.regime != "range":
        return candidates
    if snapshot.range_width < snapshot.atr * 1.4 or snapshot.avg_body < snapshot.atr * 0.1:
        return candidates

    boundary_buffer = max(snapshot.atr * 0.6, snapshot.range_width * 0.18)
    stop_buffer = snapshot.atr * style_cfg.get("stop_buffer_atr", 0.3)
    mid = (snapshot.range_high + snapshot.range_low) / 2

    if snapshot.current_price <= snapshot.range_low + boundary_buffer:
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="BUY",
            setup_type="range_reversion_long",
            regime="range",
            entry_price=snapshot.current_price,
            stop_loss=snapshot.range_low - stop_buffer,
            structure_target=max(mid, snapshot.range_high - snapshot.atr * 0.25),
            structure_score=76.0,
            reasoning="Price is rotating into validated range support where mean-reversion longs have favorable invalidation.",
            patterns=patterns,
            context_tags=["range", "mean_reversion", "support"],
        )
        if candidate:
            candidates.append(candidate)

    if snapshot.current_price >= snapshot.range_high - boundary_buffer:
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="SELL",
            setup_type="range_reversion_short",
            regime="range",
            entry_price=snapshot.current_price,
            stop_loss=snapshot.range_high + stop_buffer,
            structure_target=min(mid, snapshot.range_low + snapshot.atr * 0.25),
            structure_score=76.0,
            reasoning="Price is pressing validated range resistance where mean-reversion shorts can lean on a tight invalidation.",
            patterns=patterns,
            context_tags=["range", "mean_reversion", "resistance"],
        )
        if candidate:
            candidates.append(candidate)

    return candidates


def _detect_micro_scalp(snapshot: MarketSnapshot, secondary: Optional[MarketSnapshot], style_cfg: dict, patterns: Iterable) -> list[SetupCandidate]:
    candidates: list[SetupCandidate] = []
    if not style_cfg.get("micro_scalp"):
        return candidates
    if snapshot.timeframe != "1m":
        return candidates
    if snapshot.range_width < snapshot.atr * 1.1:
        return candidates

    micro_bias = snapshot.ema_slope / max(snapshot.atr, 0.01)
    mid = (snapshot.range_high + snapshot.range_low) / 2
    upper_lane = snapshot.range_high - snapshot.range_width * 0.18
    lower_lane = snapshot.range_low + snapshot.range_width * 0.18
    stop_buffer = snapshot.atr * style_cfg.get("stop_buffer_atr", 0.24)
    previous_high = _latest_swing(snapshot.swings, "high", skip_last=1)
    current_high = _latest_swing(snapshot.swings, "high")
    latest_low = _latest_swing(snapshot.swings, "low")
    failed_push_high = current_high["price"] if current_high else snapshot.recent_minor_high
    prior_push_high = previous_high["price"] if previous_high else snapshot.prior_minor_high
    structure_floor = latest_low["price"] if latest_low else snapshot.recent_minor_low
    lower_high_in_play = (
        prior_push_high - failed_push_high > snapshot.atr * 0.18
        and snapshot.current_price <= structure_floor + snapshot.atr * 0.1
    )

    if (
        snapshot.current_price >= mid
        and snapshot.current_price <= upper_lane
        and micro_bias > 0.015
        and snapshot.close_location > 0.5
    ):
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="BUY",
            setup_type="micro_scalp_long",
            regime=snapshot.regime if snapshot.regime != "neutral" else "micro_rotation_up",
            entry_price=snapshot.current_price,
            stop_loss=max(snapshot.current_price - snapshot.atr * 0.95, snapshot.range_low - stop_buffer),
            structure_target=max(snapshot.range_high - snapshot.atr * 0.08, snapshot.current_price + snapshot.atr * 0.75),
            structure_score=70.0,
            reasoning="Short-term order flow is rotating higher inside the active minute range, offering a nearby continuation scalp.",
            patterns=patterns,
            context_tags=["micro_scalp", "rotation", "momentum"],
        )
        if candidate:
            candidates.append(candidate)

    if (
        snapshot.current_price <= mid
        and snapshot.current_price >= lower_lane
        and micro_bias < -0.015
        and snapshot.close_location < 0.5
        and not lower_high_in_play
    ):
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="SELL",
            setup_type="micro_scalp_short",
            regime=snapshot.regime if snapshot.regime != "neutral" else "micro_rotation_down",
            entry_price=snapshot.current_price,
            stop_loss=min(snapshot.current_price + snapshot.atr * 0.95, snapshot.range_high + stop_buffer),
            structure_target=min(snapshot.range_low + snapshot.atr * 0.08, snapshot.current_price - snapshot.atr * 0.75),
            structure_score=70.0,
            reasoning="Short-term order flow is rotating lower inside the active minute range, offering a nearby continuation scalp.",
            patterns=patterns,
            context_tags=["micro_scalp", "rotation", "momentum"],
        )
        if candidate:
            candidates.append(candidate)

    return candidates


def _detect_exhaustion(snapshot: MarketSnapshot, secondary: Optional[MarketSnapshot], style_cfg: dict, patterns: Iterable) -> list[SetupCandidate]:
    candidates: list[SetupCandidate] = []
    stop_buffer = snapshot.atr * style_cfg.get("stop_buffer_atr", 0.25)

    if (
        (
            snapshot.regime in {"reversal_down", "transition", "trend_up", "breakout_up"}
            or snapshot.ema_slope > 0
        )
        and
        snapshot.upper_wick > snapshot.avg_body * 1.6
        and snapshot.relative_volume >= 0.95
        and snapshot.close_location < 0.45
    ):
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="SELL",
            setup_type="exhaustion_reversal_short",
            regime="reversal_down",
            entry_price=snapshot.current_price,
            stop_loss=snapshot.recent_high + stop_buffer,
            structure_target=snapshot.support,
            structure_score=88.0,
            reasoning="A late push into highs was rejected with heavy wick pressure, signaling a likely liquidity grab.",
            patterns=patterns,
            context_tags=["exhaustion", "liquidity_grab", "reversal"],
        )
        if candidate:
            candidates.append(candidate)

    if (
        (
            snapshot.regime in {"reversal_up", "transition", "trend_down", "breakout_down"}
            or snapshot.ema_slope < 0
        )
        and
        snapshot.lower_wick > snapshot.avg_body * 1.6
        and snapshot.relative_volume >= 0.95
        and snapshot.close_location > 0.55
    ):
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="BUY",
            setup_type="exhaustion_reversal_long",
            regime="reversal_up",
            entry_price=snapshot.current_price,
            stop_loss=snapshot.recent_low - stop_buffer,
            structure_target=snapshot.resistance,
            structure_score=88.0,
            reasoning="A flush through lows was rejected immediately, pointing to trapped sellers and a reflex bounce setup.",
            patterns=patterns,
            context_tags=["exhaustion", "liquidity_grab", "reversal"],
        )
        if candidate:
            candidates.append(candidate)

    return candidates


def _detect_supply_demand(snapshot: MarketSnapshot, secondary: Optional[MarketSnapshot], style_cfg: dict, patterns: Iterable) -> list[SetupCandidate]:
    candidates: list[SetupCandidate] = []
    if snapshot.regime in {"transition"}:
        return candidates
    
    zone_tolerance = snapshot.atr * 1.5
    stop_buffer = snapshot.atr * style_cfg.get("stop_buffer_atr", 0.35)
    
    lows = [s["price"] for s in snapshot.swings if s["type"] == "low"]
    highs = [s["price"] for s in snapshot.swings if s["type"] == "high"]
    
    valid_demand_zones = [low for low in lows if abs(snapshot.current_price - low) <= zone_tolerance and snapshot.current_price >= low - snapshot.atr * 0.2]
    
    if valid_demand_zones and snapshot.regime not in {"breakout_down", "trend_down"}:
        demand_level = min(valid_demand_zones)
        entry = snapshot.current_price
        stop = max(0.01, demand_level - stop_buffer)
        
        target = snapshot.recent_high if snapshot.recent_high > entry + snapshot.atr else entry + snapshot.atr * 2.0
        
        score_boost = 78.0
        if snapshot.current_price <= demand_level + snapshot.atr * 0.3:
            score_boost += 6.0
        if snapshot.lower_wick >= snapshot.atr * 0.4:
            score_boost += 8.0
            
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="BUY",
            setup_type="demand_zone_reaction",
            regime="pullback" if snapshot.regime.startswith("trend") else snapshot.regime,
            entry_price=entry,
            stop_loss=stop,
            structure_target=target,
            structure_score=score_boost,
            reasoning="Price has retraced into a historical structure demand zone. Accumulation is likely with defined risk below the structural low.",
            patterns=patterns,
            context_tags=["demand_zone", "structure", "accumulation"],
        )
        if candidate:
            candidates.append(candidate)

    valid_supply_zones = [high for high in highs if abs(snapshot.current_price - high) <= zone_tolerance and snapshot.current_price <= high + snapshot.atr * 0.2]
    
    if valid_supply_zones and snapshot.regime not in {"breakout_up", "trend_up"}:
        supply_level = max(valid_supply_zones)
        entry = snapshot.current_price
        stop = supply_level + stop_buffer
        
        target = snapshot.recent_low if snapshot.recent_low < entry - snapshot.atr else max(0.01, entry - snapshot.atr * 2.0)
        
        score_boost = 78.0
        if snapshot.current_price >= supply_level - snapshot.atr * 0.3:
            score_boost += 6.0
        if snapshot.upper_wick >= snapshot.atr * 0.4:
            score_boost += 8.0
            
        candidate = _build_candidate(
            snapshot=snapshot,
            secondary=secondary,
            style_cfg=style_cfg,
            direction="SELL",
            setup_type="supply_zone_reaction",
            regime="pullback" if snapshot.regime.startswith("trend") else snapshot.regime,
            entry_price=entry,
            stop_loss=stop,
            structure_target=target,
            structure_score=score_boost,
            reasoning="Price has rallied into a historical structure supply zone. Distribution is likely with defined risk above the structural high.",
            patterns=patterns,
            context_tags=["supply_zone", "structure", "distribution"],
        )
        if candidate:
            candidates.append(candidate)

    return candidates


def _resolve_by_hierarchy(
    candidates: list[SetupCandidate],
    regime_hierarchy,
    primary_atr: float,
) -> tuple[list[SetupCandidate], list[SetupCandidate]]:
    priority_map = {
        setup_type: index
        for index, setup_type in enumerate(getattr(regime_hierarchy, "allowed_detectors", []) or [])
    }
    resolved: list[SetupCandidate] = []
    rejected: list[SetupCandidate] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (priority_map.get(item.setup_type, 999), -item.score),
    ):
        conflict = next(
            (
                existing
                for existing in resolved
                if existing.direction != candidate.direction
                and abs(existing.entry_price - candidate.entry_price) <= max(primary_atr, 0.01) * 0.8
            ),
            None,
        )
        if conflict is None:
            resolved.append(candidate)
            continue

        candidate_priority = priority_map.get(candidate.setup_type, 999)
        conflict_priority = priority_map.get(conflict.setup_type, 999)
        if candidate_priority == conflict_priority and abs(candidate.score - conflict.score) <= 2.0:
            candidate.context_tags.append("hierarchy_conflict_tolerated")
            resolved.append(candidate)
            continue

        penalty = 10.0
        candidate.score = _clamp(candidate.score - penalty, 0.0, 99.0)
        candidate.evidence["conflict_penalty"] = round(penalty, 2)
        candidate.no_trade_reasons.append(
            {
                "code": "directional_conflict",
                "message": f"Conflicts with stronger {conflict.direction} candidate near the same execution zone.",
                "blocking": True,
            }
        )
        if candidate.score >= conflict.score - 2.0:
            resolved.append(candidate)
        else:
            candidate.is_rejected = True
            rejected.append(candidate)
    return resolved, rejected


def detect_ranked_setups(
    *,
    snapshots: Dict[str, MarketSnapshot],
    style_cfg: dict,
    patterns_by_timeframe: Dict[str, list],
    allowed_detectors: list[str] | None = None,
    regime_hierarchy=None,
) -> RankedSetupBook:
    primary = snapshots[style_cfg["timeframes"][0]]
    secondary = snapshots.get(style_cfg["timeframes"][1]) if len(style_cfg["timeframes"]) > 1 else None
    primary_patterns = patterns_by_timeframe.get(primary.timeframe, [])
    secondary_patterns = patterns_by_timeframe.get(secondary.timeframe, []) if secondary else []
    all_patterns = primary_patterns + secondary_patterns

    logger.info(
        f"Setup detection: regime={primary.regime} | price={primary.current_price:.2f} | "
        f"atr={primary.atr:.2f} | ema_slope={primary.ema_slope:.4f} | "
        f"body_strength={primary.body_strength:.2f} | close_loc={primary.close_location:.3f} | "
        f"range=[{primary.range_low:.2f}-{primary.range_high:.2f}] w={primary.range_width:.2f} | "
        f"compression={primary.compression_ratio:.3f} | efficiency={primary.efficiency_ratio:.3f} | "
        f"upper_wick={primary.upper_wick:.2f} | lower_wick={primary.lower_wick:.2f} | "
        f"rel_vol={primary.relative_volume:.3f}"
    )

    all_candidates: list[SetupCandidate] = []
    breakout_hits = _detect_breakout(primary, secondary, style_cfg, all_patterns)
    pullback_hits = _detect_pullback(primary, secondary, style_cfg, all_patterns)
    range_hits = _detect_range(primary, secondary, style_cfg, all_patterns)
    micro_hits = _detect_micro_scalp(primary, secondary, style_cfg, all_patterns)
    exhaustion_hits = _detect_exhaustion(primary, secondary, style_cfg, all_patterns)
    supply_demand_hits = _detect_supply_demand(primary, secondary, style_cfg, all_patterns)

    all_candidates.extend(breakout_hits)
    all_candidates.extend(pullback_hits)
    all_candidates.extend(range_hits)
    all_candidates.extend(micro_hits)
    all_candidates.extend(exhaustion_hits)
    all_candidates.extend(supply_demand_hits)

    logger.info(
        f"Detector results: breakout={len(breakout_hits)} pullback={len(pullback_hits)} "
        f"range={len(range_hits)} micro={len(micro_hits)} exhaustion={len(exhaustion_hits)} "
        f"s/d={len(supply_demand_hits)} | total={len(all_candidates)} | "
        f"allowed_detectors={allowed_detectors}"
    )

    if allowed_detectors is not None:
        filtered_candidates: list[SetupCandidate] = []
        fallback_threshold = getattr(regime_hierarchy, "fallback_override_threshold", 85.0)
        for candidate in all_candidates:
            if candidate.setup_type in allowed_detectors:
                filtered_candidates.append(candidate)
                continue
            
            # High-confidence fallback override
            if candidate.score >= fallback_threshold:
                candidate.context_tags.append("regime_gating_override")
                filtered_candidates.append(candidate)
                continue

            candidate.is_rejected = True
            candidate.no_trade_reasons.append(
                {
                    "code": "regime_gating_block",
                    "message": f"{candidate.setup_type.replace('_', ' ')} is not allowed in the active regime hierarchy.",
                    "blocking": True,
                }
            )
            candidate.context_tags.append("regime_gated")
        all_candidates = filtered_candidates + [candidate for candidate in all_candidates if candidate.is_rejected]

    rejected = [candidate for candidate in all_candidates if candidate.is_rejected]
    viable = [candidate for candidate in all_candidates if not candidate.is_rejected]
    viable, conflict_rejections = _resolve_by_hierarchy(viable, regime_hierarchy, primary.atr)
    rejected.extend(conflict_rejections)

    deduped: list[SetupCandidate] = []
    seen: set[tuple[str, str, int]] = set()
    for candidate in sorted(viable, key=lambda item: item.score, reverse=True):
        key = (candidate.setup_type, candidate.direction, round(candidate.entry_price / max(primary.atr, 0.01)))
        if key in seen:
            candidate.is_rejected = True
            candidate.no_trade_reasons.append(
                {
                    "code": "duplicate_execution_zone",
                    "message": "A stronger setup already occupies this execution zone.",
                    "blocking": True,
                }
            )
            rejected.append(candidate)
            continue
        seen.add(key)
        deduped.append(candidate)
    rejected.sort(key=lambda item: item.score, reverse=True)
    return RankedSetupBook(selected=deduped, rejected=rejected)


def _candidate_to_signal(
    *,
    candidate: SetupCandidate,
    symbol: str,
    style: str,
    batch_id: str,
    rank: int,
    is_primary: bool,
    confidence_cap: float,
) -> TradeSignal:
    confidence = _clamp(candidate.score, 0.0, confidence_cap)
    return TradeSignal(
        symbol=symbol,
        analysis_batch_id=batch_id,
        direction=candidate.direction,  # type: ignore[arg-type]
        entry_price=_round_price(candidate.entry_price),
        stop_loss=_round_price(candidate.stop_loss),
        take_profit_1=_round_price(candidate.take_profit_1),
        take_profit_2=_round_price(candidate.take_profit_2),
        confidence=round(confidence, 1),
        reasoning=candidate.reasoning,
        trading_style=style,  # type: ignore[arg-type]
        setup_type=candidate.setup_type,
        market_regime=candidate.market_regime,
        score=round(candidate.score, 1),
        rank=rank,
        is_primary=is_primary,
        entry_window_low=_round_price(candidate.entry_window_low),
        entry_window_high=_round_price(candidate.entry_window_high),
        context_tags=candidate.context_tags,
        source=candidate.source,
        evidence={key: round(float(value), 2) for key, value in candidate.evidence.items()},
        no_trade_reasons=candidate.no_trade_reasons,
    )


def build_analysis_batch(
    *,
    symbol: str,
    style: str,
    snapshots: Dict[str, MarketSnapshot],
    style_cfg: dict,
    patterns_by_timeframe: Dict[str, list],
    setup_book: RankedSetupBook | None = None,
    batch_id: str | None = None,
    allowed_detectors: list[str] | None = None,
    regime_hierarchy=None,
    confidence_cap_override: float | None = None,
) -> AnalysisBatch:
    batch_id = batch_id or str(uuid4())
    primary_snapshot = snapshots[style_cfg["timeframes"][0]]
    setup_book = setup_book or detect_ranked_setups(
        snapshots=snapshots,
        style_cfg=style_cfg,
        patterns_by_timeframe=patterns_by_timeframe,
        allowed_detectors=allowed_detectors,
        regime_hierarchy=regime_hierarchy,
    )
    candidates = setup_book.selected
    confidence_cap = 98.0 if primary_snapshot.is_live else 84.0
    if confidence_cap_override is not None:
        confidence_cap = min(confidence_cap, confidence_cap_override)

    if not candidates:
        no_trade_reasons = [
            {
                "code": "no_candidate_survived",
                "message": "No setup passed structure, conflict, and actionability filters.",
                "blocking": True,
            }
        ]
        if getattr(regime_hierarchy, "force_hold", False):
            no_trade_reasons.append(
                {
                    "code": "regime_force_hold",
                    "message": "Transition regime is active, so execution is forced to HOLD until structure stabilizes.",
                    "blocking": True,
                }
            )
        if not primary_snapshot.is_live:
            no_trade_reasons.append(
                {
                    "code": "delayed_source",
                    "message": "Only delayed data was available, so confidence was capped and execution stayed disabled.",
                    "blocking": False,
                }
            )
        if setup_book.rejected:
            top_rejected = setup_book.rejected[:2]
            no_trade_reasons.extend(
                {
                    "code": "rejected_candidate",
                    "message": f"{candidate.setup_type.replace('_', ' ')} was rejected: {(candidate.no_trade_reasons[0]['message'] if candidate.no_trade_reasons else 'another setup ranked higher')}",
                    "blocking": False,
                }
                for candidate in top_rejected
            )
        primary_signal = TradeSignal(
            symbol=symbol,
            analysis_batch_id=batch_id,
            direction="HOLD",
            entry_price=_round_price(primary_snapshot.current_price),
            stop_loss=_round_price(primary_snapshot.current_price),
            take_profit_1=_round_price(primary_snapshot.current_price),
            take_profit_2=_round_price(primary_snapshot.current_price),
            confidence=round(min(primary_snapshot.regime_confidence, confidence_cap), 1),
            reasoning=f"No trade: regime is {primary_snapshot.regime} and no setup passed structure plus spread-adjusted filters.",
            trading_style=style,  # type: ignore[arg-type]
            setup_type="no_trade",
            market_regime=primary_snapshot.regime,
            score=round(min(primary_snapshot.regime_confidence, confidence_cap), 1),
            rank=1,
            is_primary=True,
            entry_window_low=_round_price(primary_snapshot.current_price),
            entry_window_high=_round_price(primary_snapshot.current_price),
            context_tags=primary_snapshot.notes + ["no_trade"],
            source=primary_snapshot.source,
            evidence={
                "regime_alignment": round(primary_snapshot.regime_confidence, 2),
                "structure_confirmation": 0.0,
                "actionability": 0.0,
                "confluence": 0.0,
                "invalidation_quality": 0.0,
                "source_quality": 100.0 if primary_snapshot.is_live else 72.0,
                "conflict_penalty": 0.0,
                "pattern_boost": 0.0,
                "rr": 0.0,
                "proximity": 0.0,
            },
            no_trade_reasons=no_trade_reasons,
        )
        return AnalysisBatch(
            analysis_batch_id=batch_id,
            symbol=symbol,
            trading_style=style,  # type: ignore[arg-type]
            evaluated_at=datetime.now(timezone.utc),
            market_regime=primary_snapshot.regime,
            regime_summary=f"{primary_snapshot.timeframe} regime is {primary_snapshot.regime} with {primary_snapshot.boundary_touches_high}/{primary_snapshot.boundary_touches_low} boundary touches.",
            source=primary_snapshot.source,
            source_is_live=primary_snapshot.is_live,
            primary=primary_signal,
            backups=[],
        )

    selected = candidates[: 1 + style_cfg.get("max_backups", 2)]
    primary_signal = _candidate_to_signal(
        candidate=selected[0],
        symbol=symbol,
        style=style,
        batch_id=batch_id,
        rank=1,
        is_primary=True,
        confidence_cap=confidence_cap,
    )
    backups = [
        _candidate_to_signal(
            candidate=candidate,
            symbol=symbol,
            style=style,
            batch_id=batch_id,
            rank=index + 2,
            is_primary=False,
            confidence_cap=confidence_cap,
        )
        for index, candidate in enumerate(selected[1:])
    ]

    return AnalysisBatch(
        analysis_batch_id=batch_id,
        symbol=symbol,
        trading_style=style,  # type: ignore[arg-type]
        evaluated_at=datetime.now(timezone.utc),
        market_regime=primary_signal.market_regime,
        regime_summary=f"{primary_snapshot.timeframe} regime is {primary_snapshot.regime}; source={primary_snapshot.source}; ATR={primary_snapshot.atr:.2f}.",
        source=primary_snapshot.source,
        source_is_live=primary_snapshot.is_live,
        primary=primary_signal,
        backups=backups,
    )
