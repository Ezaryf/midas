"""
Sequence-aware market-state engine for ranked trade setup generation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

import pandas as pd

from app.schemas.signal import AnalysisBatch, TradeSignal


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

    regime = "neutral"
    regime_confidence = 35.0
    if touches_high >= 2 and touches_low >= 2 and efficiency < 0.45 and compression_ratio < 1.15:
        regime = "range"
        regime_confidence = 72.0
    elif float(last["close"]) >= resistance - atr * 0.03 and body_strength > 0.95 and close_location > 0.6:
        regime = "breakout_up"
        regime_confidence = 78.0
    elif float(last["close"]) <= support + atr * 0.03 and body_strength > 0.95 and close_location < 0.4:
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

    notes: list[str] = []
    if not is_live:
        notes.append("delayed_source")
    if compression_ratio < 0.9:
        notes.append("compression")
    if rel_volume > 1.25:
        notes.append("volume_expansion")

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
        notes=notes,
    )


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
) -> tuple[float, float]:
    risk = abs(entry_price - stop_loss)
    reward = abs(take_profit_1 - entry_price)
    rr = _safe_div(reward, risk, 0.0)
    proximity = 1.0 - min(abs(snapshot.current_price - entry_price) / max(snapshot.atr, 0.01), 2.0) / 2.0
    invalidation_quality = _clamp(risk / max(snapshot.atr, 0.01), 0.25, 1.75)
    invalidation_score = 12.0 - abs(invalidation_quality - 0.9) * 8.0
    confluence = 0.0
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
    return _clamp(score, 0.0, 99.0), rr


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
    score, rr = _score_candidate(
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
    if rr + 1e-6 < style_cfg["rr_min"]:
        return None

    window_half = snapshot.atr * style_cfg.get("entry_window_atr", 0.18)
    return SetupCandidate(
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
    )


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
        and snapshot.current_price >= snapshot.resistance - snapshot.atr * 0.2
        and snapshot.body_strength >= 0.9
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
        and snapshot.current_price <= snapshot.support + snapshot.atr * 0.05
        and snapshot.body_strength >= 0.85
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
        and 0.15 <= retracement <= 0.75
        and last_close > snapshot.support
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


def _detect_exhaustion(snapshot: MarketSnapshot, secondary: Optional[MarketSnapshot], style_cfg: dict, patterns: Iterable) -> list[SetupCandidate]:
    candidates: list[SetupCandidate] = []
    stop_buffer = snapshot.atr * style_cfg.get("stop_buffer_atr", 0.25)

    if (
        snapshot.regime == "reversal_down"
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
        snapshot.regime == "reversal_up"
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


def detect_ranked_setups(
    *,
    snapshots: Dict[str, MarketSnapshot],
    style_cfg: dict,
    patterns_by_timeframe: Dict[str, list],
) -> list[SetupCandidate]:
    primary = snapshots[style_cfg["timeframes"][0]]
    secondary = snapshots.get(style_cfg["timeframes"][1]) if len(style_cfg["timeframes"]) > 1 else None
    primary_patterns = patterns_by_timeframe.get(primary.timeframe, [])
    secondary_patterns = patterns_by_timeframe.get(secondary.timeframe, []) if secondary else []
    all_patterns = primary_patterns + secondary_patterns

    candidates: list[SetupCandidate] = []
    candidates.extend(_detect_breakout(primary, secondary, style_cfg, all_patterns))
    candidates.extend(_detect_pullback(primary, secondary, style_cfg, all_patterns))
    candidates.extend(_detect_range(primary, secondary, style_cfg, all_patterns))
    candidates.extend(_detect_exhaustion(primary, secondary, style_cfg, all_patterns))

    deduped: list[SetupCandidate] = []
    seen: set[tuple[str, str, int]] = set()
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        key = (candidate.setup_type, candidate.direction, round(candidate.entry_price / max(primary.atr, 0.01)))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


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
    )


def build_analysis_batch(
    *,
    symbol: str,
    style: str,
    snapshots: Dict[str, MarketSnapshot],
    style_cfg: dict,
    patterns_by_timeframe: Dict[str, list],
) -> AnalysisBatch:
    batch_id = str(uuid4())
    primary_snapshot = snapshots[style_cfg["timeframes"][0]]
    candidates = detect_ranked_setups(
        snapshots=snapshots,
        style_cfg=style_cfg,
        patterns_by_timeframe=patterns_by_timeframe,
    )
    confidence_cap = 98.0 if primary_snapshot.is_live else 84.0

    if not candidates:
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
