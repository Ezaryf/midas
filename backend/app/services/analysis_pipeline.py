from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.api.ws.mt5_handler import manager
from app.schemas.contracts import (
    AnalysisContextSummary,
    AnalysisBatchResponse,
    ExecutionConstraints,
    SourceQuality,
    TickSnapshot,
    TimeframeDatasetSummary,
)
from app.schemas.signal import (
    AnalysisBatch,
    CandidateInsight,
    DecisionGateStatus,
    EngineInsight,
    MarketPhaseSummary,
    PatternInsight,
    TradeSignal,
)
from app.services.ai_engine import AITradingEngine
from app.services.candle_source import CandleSourceResult, fetch_candles
from app.services.data_quality import (
    DataQualityContext,
    filter_signals_by_data_quality,
    get_data_quality_context,
    log_data_quality_event,
)
from app.services.execution_model import ExecutionAdjustment, ExecutionModel
from app.services.forex_factory import ForexFactoryService
from app.services.kill_switch import KillSwitch, KillSwitchContext, KillSwitchDecision
from app.services.market_state import (
    RankedSetupBook,
    build_analysis_batch,
    build_snapshot,
    detect_ranked_setups,
    determine_market_phase,
)
from app.services.pattern_recognition import PatternRecognizer, PatternType
from app.services.position_manager import PositionAction, PositionDecision, get_position_manager
from app.services.regime_gating import RegimeHierarchy, get_allowed_detectors, get_regime_hierarchy
from app.services.repositories import SignalPersistencePayload, signal_repository
from app.services.runtime_state import runtime_state
from app.services.score_calibration import ScoreCalibrator
from app.services.shadow_engine import ShadowEngine
from app.services.technical_analysis import compute_indicators

logger = logging.getLogger(__name__)


@dataclass
class AnalysisContext:
    symbol: str
    trading_style: str
    config: dict[str, Any]
    current_price: float
    tick: dict[str, Any] | None
    tick_symbol_match: bool
    tick_fresh: bool
    session_active: bool
    news_blocked: bool
    risk_blocked: bool
    datasets: dict[str, tuple[CandleSourceResult, Any]]
    patterns_by_timeframe: dict[str, list]
    snapshots: dict[str, Any]
    current_price_source: str
    generated_at: datetime
    data_quality: DataQualityContext | None = None
    regime_hierarchy: RegimeHierarchy | None = None
    kill_switch_decision: KillSwitchDecision | None = None
    execution_adjustment: ExecutionAdjustment | None = None
    effective_auto_execute_confidence: float = 0.0
    session_label: str = "off"
    transition_penalty_active: bool = False


class MarketDataService:
    def __init__(self, style_config: dict[str, dict[str, Any]]) -> None:
        self.style_config = style_config

    @staticmethod
    def _normalize_style(style: str | None) -> str:
        raw = style or runtime_state.get_trading_style() or "Scalper"
        normalized = raw.capitalize() if raw.lower() in ("scalper", "intraday", "swing") else raw
        return normalized if normalized in {"Scalper", "Intraday", "Swing"} else "Scalper"

    @staticmethod
    def _tick_freshness_seconds(config: dict[str, Any]) -> int:
        return int(config.get("tick_freshness_seconds", 90))

    @staticmethod
    def _parse_tick(tick: dict[str, Any] | None) -> tuple[dict[str, Any] | None, bool]:
        if not tick:
            return None, False
        raw_time = tick.get("time") or tick.get("received_at")
        if not raw_time:
            return tick, bool(tick.get("bid"))
        try:
            tick_time = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        except ValueError:
            return tick, bool(tick.get("bid"))
        if tick_time.tzinfo is None:
            tick_time = tick_time.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - tick_time).total_seconds()
        tick = dict(tick)
        tick["_age_seconds"] = age
        return tick, True

    @staticmethod
    def _session_label(now: datetime) -> str:
        return ExecutionModel.get_session_label(now.astimezone(timezone.utc).hour)

    async def build_context(
        self,
        *,
        trading_style: str | None,
        symbol: str | None,
        session_active: bool,
        news_blocked: bool,
        risk_blocked: bool,
    ) -> AnalysisContext:
        style = self._normalize_style(trading_style)
        target_symbol = symbol or runtime_state.get_target_symbol() or "XAUUSD"
        config = self.style_config[style]

        loop = asyncio.get_event_loop()
        runtime_tick = runtime_state.get_tick()
        tick, tick_present = self._parse_tick(runtime_tick)
        tick_symbol_match = bool(tick and tick.get("symbol") == target_symbol)
        tick_fresh = False
        if tick_present and tick:
            tick_fresh = float(tick.get("_age_seconds", self._tick_freshness_seconds(config) + 1)) <= self._tick_freshness_seconds(config)

        datasets: dict[str, tuple[CandleSourceResult, Any]] = {}
        patterns_by_timeframe: dict[str, list] = {}
        current_price: float | None = None

        for timeframe, lookback in zip(config["timeframes"], config["lookback"]):
            live_required = style == "Scalper"
            source_result = await loop.run_in_executor(
                None,
                lambda tf=timeframe, lb=lookback: fetch_candles(
                    target_symbol,
                    tf,
                    lb,
                    live_required=live_required,
                ),
            )
            if source_result is None:
                logger.warning(f"  {timeframe}: no candle source available")
                continue

            df = await loop.run_in_executor(None, compute_indicators, source_result.df)
            source_result.df = df
            datasets[timeframe] = (source_result, df)

            if current_price is None and not df.empty:
                current_price = float(df.iloc[-1]["close"])

            recognizer = PatternRecognizer(min_confidence=config["min_pattern_confidence"])
            try:
                tf_patterns = await loop.run_in_executor(None, recognizer.detect_all_patterns, df)
            except Exception as exc:
                logger.error(f"Pattern detection failed for {timeframe}: {exc}")
                tf_patterns = []

            for pattern in tf_patterns:
                pattern.timeframe = timeframe
            patterns_by_timeframe[timeframe] = tf_patterns

        primary_tf = config["timeframes"][0]
        if tick_symbol_match and tick_fresh and tick and tick.get("bid"):
            current_price = float(tick["bid"])
            current_price_source = "live_tick"
        elif primary_tf in datasets:
            current_price = current_price or float(datasets[primary_tf][1].iloc[-1]["close"])
            current_price_source = "live_candle_close" if datasets[primary_tf][0].is_live else "delayed_candle_close"
        else:
            current_price = float(tick.get("bid", 0.0)) if tick else 0.0
            current_price_source = "unavailable"

        snapshots: dict[str, Any] = {}
        for timeframe, (source_result, df) in datasets.items():
            snapshots[timeframe] = build_snapshot(
                df=df,
                timeframe=timeframe,
                source=source_result.source,
                is_live=source_result.is_live,
                current_price=current_price,
            )

        generated_at = datetime.now(timezone.utc)
        data_quality = None
        if primary_tf in datasets:
            data_quality = get_data_quality_context(
                symbol=target_symbol,
                timeframe=primary_tf,
                source_result=datasets[primary_tf][0],
            )

        return AnalysisContext(
            symbol=target_symbol,
            trading_style=style,
            config=config,
            current_price=current_price,
            tick=tick,
            tick_symbol_match=tick_symbol_match,
            tick_fresh=tick_fresh,
            session_active=session_active,
            news_blocked=news_blocked,
            risk_blocked=risk_blocked,
            datasets=datasets,
            patterns_by_timeframe=patterns_by_timeframe,
            snapshots=snapshots,
            current_price_source=current_price_source,
            generated_at=generated_at,
            data_quality=data_quality,
            effective_auto_execute_confidence=float(os.getenv("AUTO_EXECUTE_MIN_CONFIDENCE", str(config["auto_execute_confidence"]))),
            session_label=self._session_label(generated_at),
        )


class SignalRankingService:
    CANDLESTICK_PATTERN_TYPES = {
        PatternType.HAMMER.value,
        PatternType.INVERTED_HAMMER.value,
        PatternType.SHOOTING_STAR.value,
        PatternType.HANGING_MAN.value,
        PatternType.ENGULFING_BULL.value,
        PatternType.ENGULFING_BEAR.value,
        PatternType.MORNING_STAR.value,
        PatternType.EVENING_STAR.value,
        PatternType.DOJI.value,
        PatternType.DRAGONFLY_DOJI.value,
        PatternType.GRAVESTONE_DOJI.value,
        PatternType.THREE_WHITE_SOLDIERS.value,
        PatternType.THREE_BLACK_CROWS.value,
        PatternType.PIERCING_LINE.value,
        PatternType.DARK_CLOUD_COVER.value,
    }

    @classmethod
    def _pattern_family(cls, pattern_type: str) -> str:
        return "candlestick" if pattern_type in cls.CANDLESTICK_PATTERN_TYPES else "chart"

    @classmethod
    def _matching_pattern_insights(
        cls,
        *,
        direction: str,
        entry_price: float,
        tolerance: float,
        patterns_by_timeframe: dict[str, list],
        reference_direction: str | None = None,
    ) -> list[PatternInsight]:
        matches: list[PatternInsight] = []
        for timeframe, tf_patterns in patterns_by_timeframe.items():
            for pattern in tf_patterns:
                pattern_direction = getattr(pattern, "direction", "")
                candidate_entry = float(getattr(pattern, "entry_price", entry_price))
                if pattern_direction != direction or abs(candidate_entry - entry_price) > tolerance:
                    continue
                relation = "neutral"
                if reference_direction in {"BUY", "SELL"}:
                    relation = "support" if pattern_direction == reference_direction else "conflict"
                matches.append(
                    PatternInsight(
                        type=getattr(getattr(pattern, "type", None), "value", str(getattr(pattern, "type", "pattern"))),
                        family=cls._pattern_family(
                            getattr(getattr(pattern, "type", None), "value", str(getattr(pattern, "type", "pattern")))
                        ),  # type: ignore[arg-type]
                        timeframe=timeframe,
                        direction=pattern_direction,  # type: ignore[arg-type]
                        confidence=round(float(getattr(pattern, "confidence", 0.0)), 1),
                        description=getattr(pattern, "description", ""),
                        relation=relation,  # type: ignore[arg-type]
                        entry_price=round(candidate_entry, 2),
                    )
                )
        matches.sort(key=lambda item: item.confidence, reverse=True)
        return matches[:3]

    @staticmethod
    def build_no_data_batch(context: AnalysisContext) -> AnalysisBatch:
        live_only_mode = context.trading_style == "Scalper"
        reason_code = "no_live_primary_data" if live_only_mode else "insufficient_candle_data"
        reason_message = (
            "Live MT5 candles were unavailable for the configured scalper timeframes."
            if live_only_mode
            else "No usable candle datasets were available for the configured primary timeframe."
        )
        hold = TradeSignal(
            symbol=context.symbol,
            direction="HOLD",
            entry_price=context.current_price,
            stop_loss=context.current_price,
            take_profit_1=context.current_price,
            take_profit_2=context.current_price,
            confidence=0,
            reasoning=(
                "No trade: live MT5 candle feed is unavailable for scalper execution."
                if live_only_mode
                else "No trade: insufficient candle data from MT5 and fallback sources."
            ),
            trading_style=context.trading_style,  # type: ignore[arg-type]
            setup_type="no_data",
            market_regime="unknown",
            score=0,
            rank=1,
            is_primary=True,
            entry_window_low=context.current_price,
            entry_window_high=context.current_price,
            context_tags=["no_data", context.current_price_source],
            source="unavailable",
            no_trade_reasons=[
                {
                    "code": reason_code,
                    "message": reason_message,
                    "blocking": True,
                }
            ],
        )
        return AnalysisBatch(
            analysis_batch_id="no-data",
            symbol=context.symbol,
            trading_style=context.trading_style,  # type: ignore[arg-type]
            evaluated_at=context.generated_at,
            market_regime="unknown",
            regime_summary="No analysis batch generated because no usable candles were available.",
            source="unavailable",
            source_is_live=False,
            context_summary={},
            primary=hold,
            backups=[],
        )

    @classmethod
    def attach_pattern_matches(cls, batch: AnalysisBatch, snapshots: dict[str, Any], patterns_by_timeframe: dict[str, list], primary_tf: str) -> None:
        primary_snapshot = snapshots[primary_tf]
        tolerance = max(getattr(primary_snapshot, "atr", 1.0) * 1.2, 0.1)

        def to_signal_patterns(signal: TradeSignal) -> list[dict]:
            return [
                {
                    "type": pattern.type,
                    "confidence": pattern.confidence,
                    "description": pattern.description,
                }
                for pattern in cls._matching_pattern_insights(
                    direction=signal.direction,
                    entry_price=signal.entry_price,
                    tolerance=tolerance,
                    patterns_by_timeframe=patterns_by_timeframe,
                    reference_direction=batch.primary.direction,
                )
            ]

        batch.primary.patterns = to_signal_patterns(batch.primary)
        for backup in batch.backups:
            backup.patterns = to_signal_patterns(backup)

    @staticmethod
    def build_context_summary(context: AnalysisContext) -> AnalysisContextSummary:
        tick_snapshot = None
        if context.tick:
            tick_time = context.tick.get("time")
            received_at = context.tick.get("received_at")
            tick_snapshot = TickSnapshot(
                symbol=context.tick.get("symbol"),
                bid=context.tick.get("bid"),
                ask=context.tick.get("ask"),
                spread=context.tick.get("spread"),
                time=datetime.fromisoformat(str(tick_time).replace("Z", "+00:00")) if tick_time else None,
                received_at=datetime.fromisoformat(str(received_at).replace("Z", "+00:00")) if received_at else None,
            )

        dataset_summaries: list[TimeframeDatasetSummary] = []
        for timeframe, (source_result, df) in context.datasets.items():
            allowed_strategy_class = None
            freshness_passed = source_result.freshness_ok
            if context.data_quality and timeframe == context.config["timeframes"][0]:
                allowed_strategy_class = context.data_quality.allowed_strategy_class
                freshness_passed = context.data_quality.freshness_passed
            dataset_summaries.append(
                TimeframeDatasetSummary(
                    timeframe=timeframe,
                    source=source_result.source,
                    is_live=source_result.is_live,
                    candles=len(df),
                    source_quality=SourceQuality(
                        symbol_match=context.tick_symbol_match,
                        tick_fresh=context.tick_fresh,
                        source=source_result.source,
                        is_live=source_result.is_live,
                        confidence_cap=source_result.confidence_cap,
                        age_seconds=source_result.age_seconds,
                        freshness_passed=freshness_passed,
                        allowed_strategy_class=allowed_strategy_class,
                        notes=source_result.notes + [context.current_price_source],
                    ),
                )
            )

        return AnalysisContextSummary(
            symbol=context.symbol,
            trading_style=context.trading_style,  # type: ignore[arg-type]
            current_price=round(float(context.current_price), 2),
            tick=tick_snapshot,
            datasets=dataset_summaries,
            session_active=context.session_active,
            news_blocked=context.news_blocked,
            risk_blocked=context.risk_blocked,
            primary_regime_stability=(
                round(float(context.snapshots[context.config["timeframes"][0]].regime_stability), 2)
                if context.config["timeframes"][0] in context.snapshots
                else None
            ),
            primary_data_age_seconds=context.data_quality.age_seconds if context.data_quality else None,
            primary_freshness_passed=context.data_quality.freshness_passed if context.data_quality else None,
            kill_switch={
                "halt_trading": bool(context.kill_switch_decision.halt_trading) if context.kill_switch_decision else False,
                "require_manual_approval": bool(context.kill_switch_decision.require_manual_approval) if context.kill_switch_decision else False,
                "size_multiplier": float(context.kill_switch_decision.size_multiplier) if context.kill_switch_decision else 1.0,
                "reasons": list(context.kill_switch_decision.reasons) if context.kill_switch_decision else [],
            },
            constraints=ExecutionConstraints(
                auto_execute_confidence=float(context.effective_auto_execute_confidence),
                rr_min=float(context.config["rr_min"]),
                rr_target=float(context.config["rr_target"]),
                max_backups=int(context.config["max_backups"]),
            ),
            generated_at=context.generated_at,
        )

    @classmethod
    def build_engine_insight(
        cls,
        *,
        context: AnalysisContext,
        batch: AnalysisBatch,
        setup_book: RankedSetupBook,
        context_summary: AnalysisContextSummary,
    ) -> EngineInsight:
        primary_tf = context.config["timeframes"][0]
        primary_snapshot = context.snapshots.get(primary_tf)
        if primary_snapshot:
            phase_key, phase_label, phase_description = determine_market_phase(primary_snapshot)
            tolerance = max(getattr(primary_snapshot, "atr", 1.0) * 1.2, 0.1)
            source_is_live = primary_snapshot.is_live
            source_name = primary_snapshot.source
        else:
            phase_key, phase_label, phase_description = ("compression", "Compression", "The engine is waiting for enough structure to classify the market.")
            tolerance = 0.1
            source_is_live = False
            source_name = "unavailable"

        reference_direction = batch.primary.direction if batch.primary.direction in {"BUY", "SELL"} else None
        pattern_tape: list[PatternInsight] = []
        for timeframe, tf_patterns in context.patterns_by_timeframe.items():
            for pattern in tf_patterns:
                pattern_direction = getattr(pattern, "direction", "")
                if pattern_direction not in {"BUY", "SELL"}:
                    continue
                relation = "neutral"
                if reference_direction:
                    relation = "support" if pattern_direction == reference_direction else "conflict"
                pattern_tape.append(
                    PatternInsight(
                        type=getattr(getattr(pattern, "type", None), "value", str(getattr(pattern, "type", "pattern"))),
                        family=cls._pattern_family(
                            getattr(getattr(pattern, "type", None), "value", str(getattr(pattern, "type", "pattern")))
                        ),  # type: ignore[arg-type]
                        timeframe=timeframe,
                        direction=pattern_direction,  # type: ignore[arg-type]
                        confidence=round(float(getattr(pattern, "confidence", 0.0)), 1),
                        description=getattr(pattern, "description", ""),
                        relation=relation,  # type: ignore[arg-type]
                        entry_price=round(float(getattr(pattern, "entry_price", context.current_price)), 2),
                    )
                )
        pattern_tape.sort(key=lambda item: item.confidence, reverse=True)

        def signal_candidate(signal: TradeSignal, status: str) -> CandidateInsight:
            linked_patterns = cls._matching_pattern_insights(
                direction=signal.direction,
                entry_price=signal.entry_price,
                tolerance=tolerance,
                patterns_by_timeframe=context.patterns_by_timeframe,
                reference_direction=reference_direction,
            )
            return CandidateInsight(
                setup_type=signal.setup_type or "manual",
                direction=signal.direction,
                status=status,  # type: ignore[arg-type]
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit_1=signal.take_profit_1,
                take_profit_2=signal.take_profit_2,
                score=round(float(signal.score or signal.confidence), 1),
                rr=round(float(signal.evidence.get("rr", 0.0)) if signal.evidence else 0.0, 4),
                evidence=signal.evidence or {},
                blocker_reasons=signal.no_trade_reasons or [],
                context_tags=signal.context_tags or [],
                linked_patterns=linked_patterns,
                reasoning=signal.reasoning,
            )

        def rejected_candidate(candidate: Any) -> CandidateInsight:
            linked_patterns = cls._matching_pattern_insights(
                direction=candidate.direction,
                entry_price=candidate.entry_price,
                tolerance=tolerance,
                patterns_by_timeframe=context.patterns_by_timeframe,
                reference_direction=reference_direction,
            )
            return CandidateInsight(
                setup_type=candidate.setup_type,
                direction=candidate.direction,  # type: ignore[arg-type]
                status="rejected",
                entry_price=round(float(candidate.entry_price), 2),
                stop_loss=round(float(candidate.stop_loss), 2),
                take_profit_1=round(float(candidate.take_profit_1), 2),
                take_profit_2=round(float(candidate.take_profit_2), 2),
                score=round(float(candidate.score), 1),
                rr=round(float(candidate.rr), 4),
                evidence={key: round(float(value), 2) for key, value in candidate.evidence.items()},
                blocker_reasons=candidate.no_trade_reasons,
                context_tags=candidate.context_tags,
                linked_patterns=linked_patterns,
                reasoning=candidate.reasoning,
            )

        candidates: list[CandidateInsight] = []
        candidates.append(signal_candidate(batch.primary, "selected"))
        candidates.extend(signal_candidate(backup, "backup") for backup in batch.backups)
        candidates.extend(rejected_candidate(candidate) for candidate in setup_book.rejected[:4])

        confidence_cap = max(
            [dataset.source_quality.confidence_cap for dataset in context_summary.datasets],
            default=0.0,
        )
        decision_gates = [
            DecisionGateStatus(
                code="session_active",
                label="Session",
                passed=context.session_active,
                detail="Trading session is active." if context.session_active else "Session filter is blocking new execution.",
                blocking=not context.session_active,
            ),
            DecisionGateStatus(
                code="news_clear",
                label="News",
                passed=not context.news_blocked,
                detail="No macro blackout is active." if not context.news_blocked else "News blackout is active around a high-impact event.",
                blocking=context.news_blocked,
            ),
            DecisionGateStatus(
                code="risk_clear",
                label="Risk",
                passed=not context.risk_blocked,
                detail="Risk engine allows new exposure." if not context.risk_blocked else "Risk engine is blocking new exposure.",
                blocking=context.risk_blocked,
            ),
            DecisionGateStatus(
                code="symbol_match",
                label="Symbol Match",
                passed=context.tick_symbol_match,
                detail="Live tick matches the selected symbol." if context.tick_symbol_match else "Latest live tick does not match the selected symbol.",
                blocking=not context.tick_symbol_match,
            ),
            DecisionGateStatus(
                code="tick_fresh",
                label="Tick Freshness",
                passed=context.tick_fresh,
                detail="Live tick is fresh enough for execution." if context.tick_fresh else "Live tick is stale or missing, so execution confidence is reduced.",
                blocking=not context.tick_fresh,
            ),
            DecisionGateStatus(
                code="source_live",
                label="Source",
                passed=source_is_live,
                detail=f"Primary dataset is live from {source_name}." if source_is_live else f"Primary dataset is delayed from {source_name}.",
                blocking=not source_is_live,
            ),
            DecisionGateStatus(
                code="data_quality",
                label="Data Freshness",
                passed=bool(context.data_quality.freshness_passed) if context.data_quality else False,
                detail=(
                    f"Primary data is {context.data_quality.age_bars:.2f} bars old and allows {context.data_quality.allowed_strategy_class} strategies."
                    if context.data_quality
                    else "No primary data-quality context was available."
                ),
                blocking=bool(context.data_quality.hard_block) if context.data_quality else True,
            ),
            DecisionGateStatus(
                code="confidence_cap",
                label="Confidence Cap",
                passed=confidence_cap >= context.effective_auto_execute_confidence,
                detail=f"Source quality caps confidence at {confidence_cap:.0f}.",
                blocking=confidence_cap < float(context.effective_auto_execute_confidence),
            ),
            DecisionGateStatus(
                code="kill_switch",
                label="Kill Switch",
                passed=not bool(context.kill_switch_decision and (context.kill_switch_decision.halt_trading or context.kill_switch_decision.require_manual_approval)),
                detail=(
                    "Kill switch clear."
                    if not context.kill_switch_decision or not context.kill_switch_decision.reasons
                    else f"Kill switch active: {', '.join(context.kill_switch_decision.reasons)}"
                ),
                blocking=bool(context.kill_switch_decision and context.kill_switch_decision.halt_trading),
            ),
        ]

        summary = (
            f"{phase_label} on {primary_tf.upper()} with {batch.market_regime.replace('_', ' ')} regime. "
            f"{len(setup_book.selected)} executable candidate(s) and {len(setup_book.rejected)} rejected idea(s) were ranked."
        )

        return EngineInsight(
            phase=MarketPhaseSummary(
                key=phase_key,
                label=phase_label,
                description=phase_description,
            ),
            summary=summary,
            candidates=candidates,
            patterns=pattern_tape[:8],
            decision_gates=decision_gates,
        )


class SignalPublisher:
    def __init__(self, websocket_manager: Any) -> None:
        self.manager = websocket_manager
        self._background_tasks: set[asyncio.Task] = set()

    async def persist_and_broadcast(self, batch: AnalysisBatch, context: AnalysisContext) -> AnalysisBatch:
        provider, api_key = runtime_state.get_ai_preferences()
        if not provider:
            provider = "openai"

        primary_tf = context.config["timeframes"][0]
        ff = ForexFactoryService()
        try:
            calendar_events = ff.get_weekly_events()[:5]
        except Exception as exc:
            logger.warning(f"Calendar fetch failed during publish: {exc}")
            calendar_events = []

        primary_snapshot = context.snapshots.get(primary_tf)
        primary_dataset = context.datasets.get(primary_tf)
        primary_row = primary_dataset[1].iloc[-1] if primary_dataset else None
        indicators = {
            "RSI_14": round(float(primary_row.get("RSI_14", 50.0)), 2) if primary_row is not None else 50.0,
            "MACD_12_26_9": round(float(primary_row.get("MACDh_12_26_9", 0.0)), 4) if primary_row is not None else 0.0,
            "ATRr_14": round(float(primary_row.get("ATRr_14", getattr(primary_snapshot, "atr", 0.0))), 2) if primary_row is not None else round(float(getattr(primary_snapshot, "atr", 0.0) or 0.0), 2),
            "EMA_9": round(float(primary_row.get("EMA_9", 0.0)), 2) if primary_row is not None else 0.0,
            "EMA_21": round(float(primary_row.get("EMA_21", 0.0)), 2) if primary_row is not None else 0.0,
            "EMA_50": round(float(primary_row.get("EMA_50", 0.0)), 2) if primary_row is not None else 0.0,
            "symbol": context.symbol,
        }
        trend = getattr(primary_snapshot, "regime", batch.market_regime or "neutral").upper()

        execution_tradeable = True if not context.execution_adjustment else bool(context.execution_adjustment.tradeable)
        primary_should_auto_execute = (
            batch.primary.direction in ("BUY", "SELL")
            and batch.primary.confidence >= context.effective_auto_execute_confidence
            and context.session_active
            and not context.news_blocked
            and not context.risk_blocked
            and not batch.primary.is_duplicate
            and batch.primary.position_action in {
                PositionAction.OPEN.value,
                PositionAction.REVERSE.value,
                PositionAction.SCALE_IN.value,
            }
            and not bool(context.kill_switch_decision and (context.kill_switch_decision.halt_trading or context.kill_switch_decision.require_manual_approval))
            and execution_tradeable
        )

        if primary_should_auto_execute:
            position_manager = get_position_manager()
            position_manager.mark_signal_emitted(
                batch.primary.symbol or context.symbol,
                batch.primary.direction,
            )

        position_manager = get_position_manager()
        for signal in [batch.primary, *batch.backups]:
            signal_id = signal_repository.save(
                SignalPersistencePayload(
                    signal=signal,
                    indicators=indicators,
                    calendar_events=calendar_events,
                    current_price=context.current_price,
                    trend=trend,
                    ai_provider=provider if api_key else "deterministic",
                    ai_model="bounded-explainer" if api_key else "rule-engine",
                    regime_summary=batch.regime_summary,
                )
            )
            if signal_id not in {"db_disabled", "error"}:
                signal.signal_id = signal_id
                signal.id = signal_id
                try:
                    from app.services.database import db

                    db.bind_shadow_signal(
                        analysis_batch_id=signal.analysis_batch_id,
                        setup_type=signal.setup_type,
                        direction=signal.direction,
                        signal_id=signal_id,
                    )
                except Exception:
                    pass
            logged_action = signal.position_action or PositionAction.IGNORE.value
            position_manager.log_decision(
                signal_id=signal.signal_id,
                symbol=signal.symbol or context.symbol,
                signal_direction=signal.direction,
                signal_confidence=float(signal.confidence),
                decision=PositionDecision(
                    action=PositionAction(logged_action),
                    reason=signal.position_action_reason or "",
                    position=position_manager.get_current_position(signal.symbol or context.symbol),
                ),
                executed=False,
                execution_result="queued_for_dispatch" if signal is batch.primary and primary_should_auto_execute else signal.position_action_reason,
            )

        batch_payload = batch.model_dump(mode="json")
        await self.manager.broadcast_json({"type": "SIGNAL_BATCH", "data": batch_payload})

        primary_payload = batch.primary.model_dump(mode="json")
        primary_payload["session_label"] = context.session_label
        primary_payload["volatility_bucket"] = context.execution_adjustment.volatility_bucket if context.execution_adjustment else "medium"
        primary_payload["auto_execute"] = primary_should_auto_execute
        await self.manager.broadcast_json(
            {
                "type": "SIGNAL",
                "action": "PLACE_ORDER" if primary_payload["auto_execute"] else "DISPLAY",
                "data": primary_payload,
            }
        )

        if primary_snapshot is not None:
            await self.manager.broadcast_json(
                {
                    "type": "MARKET_STATE",
                    "data": {
                        "timeframe": primary_snapshot.timeframe,
                        "source": primary_snapshot.source,
                        "is_live": primary_snapshot.is_live,
                        "current_price": round(primary_snapshot.current_price, 2),
                        "atr": round(primary_snapshot.atr, 2),
                        "avg_body": round(primary_snapshot.avg_body, 2),
                        "body_strength": round(primary_snapshot.body_strength, 3),
                        "upper_wick": round(primary_snapshot.upper_wick, 2),
                        "lower_wick": round(primary_snapshot.lower_wick, 2),
                        "close_location": round(primary_snapshot.close_location, 3),
                        "relative_volume": round(primary_snapshot.relative_volume, 3),
                        "efficiency_ratio": round(primary_snapshot.efficiency_ratio, 3),
                        "compression_ratio": round(primary_snapshot.compression_ratio, 3),
                        "ema_slope": round(primary_snapshot.ema_slope, 4),
                        "range_high": round(primary_snapshot.range_high, 2),
                        "range_low": round(primary_snapshot.range_low, 2),
                        "range_width": round(primary_snapshot.range_width, 2),
                        "boundary_touches_high": primary_snapshot.boundary_touches_high,
                        "boundary_touches_low": primary_snapshot.boundary_touches_low,
                        "recent_high": round(primary_snapshot.recent_high, 2),
                        "recent_low": round(primary_snapshot.recent_low, 2),
                        "support": round(primary_snapshot.support, 2),
                        "resistance": round(primary_snapshot.resistance, 2),
                        "recent_minor_high": round(primary_snapshot.recent_minor_high, 2),
                        "prior_minor_high": round(primary_snapshot.prior_minor_high, 2),
                        "recent_minor_low": round(primary_snapshot.recent_minor_low, 2),
                        "prior_minor_low": round(primary_snapshot.prior_minor_low, 2),
                        "swings": primary_snapshot.swings,
                        "regime": primary_snapshot.regime,
                        "regime_confidence": round(primary_snapshot.regime_confidence, 1),
                        "regime_stability": round(primary_snapshot.regime_stability, 2),
                        "regime_history": primary_snapshot.regime_history,
                        "phase_key": batch.engine_insight.phase.key if batch.engine_insight else None,
                        "phase_label": batch.engine_insight.phase.label if batch.engine_insight else None,
                        "phase_description": batch.engine_insight.phase.description if batch.engine_insight else None,
                        "notes": primary_snapshot.notes,
                        "data_age_seconds": context.data_quality.age_seconds if context.data_quality else None,
                        "freshness_passed": context.data_quality.freshness_passed if context.data_quality else None,
                        "allowed_strategy_class": context.data_quality.allowed_strategy_class if context.data_quality else None,
                        "kill_switch": {
                            "halt_trading": bool(context.kill_switch_decision.halt_trading) if context.kill_switch_decision else False,
                            "require_manual_approval": bool(context.kill_switch_decision.require_manual_approval) if context.kill_switch_decision else False,
                            "size_multiplier": float(context.kill_switch_decision.size_multiplier) if context.kill_switch_decision else 1.0,
                            "reasons": list(context.kill_switch_decision.reasons) if context.kill_switch_decision else [],
                        },
                        "symbol": context.symbol,
                        "trading_style": context.trading_style,
                        "context_summary": batch.context_summary,
                    },
                }
            )

        if api_key and batch.primary.direction in ("BUY", "SELL") and getattr(batch.primary, "signal_id", None) not in {None, "db_disabled", "error"}:
            task = asyncio.create_task(self._async_explain_and_update(batch, provider, api_key, batch.primary.signal_id))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

        return batch

    async def _async_explain_and_update(self, batch: AnalysisBatch, provider: str, api_key: str, signal_id: str):
        try:
            explained_batch = await AITradingEngine.explain_batch_with_fallback(
                batch=batch,
                primary_provider=provider,
                primary_api_key=api_key,
            )
            reasoning = explained_batch.primary.reasoning
            from app.services.repositories import signal_repository
            signal_repository.update_reasoning(
                signal_id=signal_id,
                reasoning=reasoning,
                ai_provider=provider,
                ai_model="bounded-explainer"
            )
            
            await self.manager.broadcast_json({
                "type": "SIGNAL_UPDATE",
                "data": {
                    "id": signal_id,
                    "reasoning": reasoning
                }
            })
        except Exception as exc:
            logger.error(f"Async AI explanation failed: {exc}")


class TradingEngine:
    def __init__(self, style_config: dict[str, dict[str, Any]]) -> None:
        self.market_data = MarketDataService(style_config)
        self.ranking = SignalRankingService()
        self.publisher = SignalPublisher(manager)
        self.shadow_engine = ShadowEngine()
        self.position_manager = get_position_manager()

    @staticmethod
    def _volatility_ratio(snapshot: Any) -> float:
        baseline = max(float(getattr(snapshot, "avg_body", 0.0)), 0.01)
        return round(float(getattr(snapshot, "atr", 0.0)) / baseline, 4)

    @staticmethod
    def _apply_hold_reason(batch: AnalysisBatch, *, reason_code: str, message: str) -> None:
        if batch.primary.direction == "HOLD":
            batch.primary.no_trade_reasons.append({"code": reason_code, "message": message, "blocking": True})

    def _log_shadow_candidates(self, *, batch_id: str, context: AnalysisContext, setup_book: RankedSetupBook) -> None:
        primary_tf = context.config["timeframes"][0]
        primary_snapshot = context.snapshots.get(primary_tf)
        if not primary_snapshot:
            return
        volatility_ratio = self._volatility_ratio(primary_snapshot)
        spread_estimate = float((context.tick or {}).get("spread") or 0.0)
        candidates = [*setup_book.selected, *setup_book.rejected]
        for index, candidate in enumerate(candidates, start=1):
            self.shadow_engine.log_candidate(
                candidate=candidate,
                analysis_batch_id=batch_id,
                symbol=context.symbol,
                trading_style=context.trading_style,
                timeframe=primary_tf,
                regime_confidence=float(getattr(primary_snapshot, "regime_confidence", 0.0)),
                compression_ratio=float(getattr(primary_snapshot, "compression_ratio", 1.0)),
                data_freshness=context.data_quality.allowed_strategy_class if context.data_quality else "unknown",
                spread_estimate=spread_estimate,
                volatility_ratio=volatility_ratio,
                signal_timestamp=context.generated_at,
                rank=index,
            )

    def _apply_signal_adjustments(self, *, batch: AnalysisBatch, context: AnalysisContext) -> None:
        primary_tf = context.config["timeframes"][0]
        primary_snapshot = context.snapshots[primary_tf]
        current_spread = float((context.tick or {}).get("spread") or 0.0)
        if current_spread > 0:
            ExecutionModel.observe_spread(context.symbol, current_spread)

        volatility_bucket = ExecutionModel.get_volatility_bucket(self._volatility_ratio(primary_snapshot))
        if current_spread <= 0:
            current_spread = ExecutionModel.get_spread_estimate(context.symbol, context.session_label, volatility_bucket)
        execution_adjustment = ExecutionModel.apply_execution_correction(
            symbol=context.symbol,
            direction=batch.primary.direction,
            regime=batch.market_regime,
            session=context.session_label,
            volatility_bucket=volatility_bucket,
            current_spread=current_spread,
            entry_price=batch.primary.entry_price,
        )
        context.execution_adjustment = execution_adjustment

        confidence_cap = 99.0
        if context.regime_hierarchy:
            confidence_cap = min(confidence_cap, context.regime_hierarchy.confidence_cap * 100.0)

        signals = [batch.primary, *batch.backups]
        for signal in signals:
            calibration = ScoreCalibrator.get_calibrated_confidence(
                raw_score=float(signal.score or 0.0),
                market_regime=signal.market_regime,
                session=context.session_label,
                execution_multiplier=execution_adjustment.confidence_multiplier * (
                    context.regime_hierarchy.confidence_boost if context.regime_hierarchy else 1.0
                ),
                setup_type=signal.setup_type,
            )
            signal.evidence["calibrated_confidence"] = calibration.calibrated_confidence
            signal.evidence["empirical_win_rate"] = calibration.empirical_win_rate
            signal.evidence["calibration_sample_size"] = calibration.calibration_sample_size
            signal.evidence["baseline_win_rate"] = calibration.baseline_win_rate
            signal.evidence["execution_confidence_multiplier"] = execution_adjustment.confidence_multiplier
            signal.evidence["execution_spread"] = execution_adjustment.current_spread
            signal.evidence["typical_spread"] = execution_adjustment.typical_spread
            signal.evidence["execution_tradeable"] = 1.0 if execution_adjustment.tradeable else 0.0
            signal.evidence["compression_ratio"] = round(float(primary_snapshot.compression_ratio), 4)
            signal.evidence["efficiency_ratio"] = round(float(primary_snapshot.efficiency_ratio), 4)
            signal.evidence["close_location"] = round(float(primary_snapshot.close_location), 4)
            signal.evidence["body_strength"] = round(float(primary_snapshot.body_strength), 4)
            signal.calibrated_confidence = calibration.calibrated_confidence
            signal.confidence_source = "execution_adjusted"
            signal.confidence = round(min(calibration.calibrated_confidence, confidence_cap), 1)

            if execution_adjustment.reason:
                signal.context_tags.append(execution_adjustment.reason)
            if not execution_adjustment.tradeable:
                signal.no_trade_reasons.append(
                    {
                        "code": "execution_not_tradeable",
                        "message": "Execution friction is above the acceptable spread threshold for live trading.",
                        "blocking": True,
                    }
                )
            if batch.market_regime == "transition":
                signal.context_tags.append("transition_regime_reduced_confidence")

    def _apply_position_decisions(self, *, batch: AnalysisBatch, context: AnalysisContext) -> None:
        signals = [batch.primary, *batch.backups]
        annotated = self.position_manager.filter_signals(signals, context.symbol)
        for signal, decision, is_duplicate in annotated:
            action = decision.action
            reason = decision.reason
            if is_duplicate:
                action = PositionAction.IGNORE
                reason = (
                    f"Duplicate {signal.direction} signal suppressed within "
                    f"{self.position_manager.config.cooldown_seconds}s cooldown."
                )
                signal.context_tags.append("duplicate_signal")
                signal.no_trade_reasons.append(
                    {
                        "code": "duplicate_signal",
                        "message": reason,
                        "blocking": False,
                    }
                )
            elif action == PositionAction.IGNORE and signal.direction in {"BUY", "SELL"}:
                signal.no_trade_reasons.append(
                    {
                        "code": "position_action_ignore",
                        "message": reason,
                        "blocking": False,
                    }
                )

            signal.position_action = action.value
            signal.position_action_reason = reason
            signal.is_duplicate = is_duplicate
            signal.context_tags.append(f"position_action:{action.value}")

    def _evaluate_kill_switch(self, *, context: AnalysisContext) -> KillSwitchDecision:
        primary_tf = context.config["timeframes"][0]
        primary_snapshot = context.snapshots.get(primary_tf)
        current_spread = float((context.tick or {}).get("spread") or 0.0)
        typical_spread = float(context.execution_adjustment.typical_spread) if context.execution_adjustment else current_spread
        drawdown_pct = 0.0
        consecutive_losses = 0
        try:
            from app.services.risk_manager import get_risk_manager
            from app.services.trading_state import trading_state

            risk_manager = get_risk_manager()
            if risk_manager:
                account = risk_manager.get_account_info()
                balance = float(account.get("balance", 0.0) or 0.0)
                equity = float(account.get("equity", 0.0) or 0.0)
                if balance > 0:
                    drawdown_pct = ((balance - equity) / balance) * 100.0
            consecutive_losses = int(getattr(trading_state, "consecutive_losses", 0))
        except Exception:
            drawdown_pct = 0.0
            consecutive_losses = 0

        decision = KillSwitch.check(
            KillSwitchContext(
                symbol=context.symbol,
                data_age_seconds=float(context.data_quality.age_seconds) if context.data_quality else 0.0,
                regime_stability=float(getattr(primary_snapshot, "regime_stability", 1.0)) if primary_snapshot else 1.0,
                current_spread=current_spread,
                typical_spread=typical_spread,
                drawdown_pct=drawdown_pct,
                consecutive_losses=consecutive_losses,
                transition_cluster=context.transition_penalty_active or bool(primary_snapshot and primary_snapshot.regime == "transition"),
            )
        )
        if decision.reasons:
            KillSwitch.log_event(
                symbol=context.symbol,
                decision=decision,
                context={
                    "data_age_seconds": float(context.data_quality.age_seconds) if context.data_quality else None,
                    "regime_stability": float(getattr(primary_snapshot, "regime_stability", 1.0)) if primary_snapshot else None,
                    "current_spread": current_spread,
                    "typical_spread": typical_spread,
                    "session": context.session_label,
                },
            )
        return decision

    async def analyze(
        self,
        *,
        trading_style: str | None,
        symbol: str | None,
        session_active: bool,
        news_blocked: bool,
        risk_blocked: bool,
        publish: bool = True,
        transition_penalty_active: bool = False,
    ) -> AnalysisBatchResponse:
        context = await self.market_data.build_context(
            trading_style=trading_style,
            symbol=symbol,
            session_active=session_active,
            news_blocked=news_blocked,
            risk_blocked=risk_blocked,
        )
        context.transition_penalty_active = transition_penalty_active
        base_auto_execute_confidence = float(
            os.getenv("AUTO_EXECUTE_MIN_CONFIDENCE", str(context.config["auto_execute_confidence"]))
        )
        primary_tf = context.config["timeframes"][0]
        setup_book = RankedSetupBook()
        if primary_tf not in context.datasets:
            batch = self.ranking.build_no_data_batch(context)
        else:
            primary_snapshot = context.snapshots[primary_tf]
            context.regime_hierarchy = get_regime_hierarchy(primary_snapshot.regime, primary_snapshot)
            transition_multiplier = 1.05 if transition_penalty_active else 1.0
            regime_threshold_cap = max(50.0, (context.regime_hierarchy.confidence_cap * 100.0) - 4.0)
            context.effective_auto_execute_confidence = min(
                base_auto_execute_confidence * transition_multiplier,
                regime_threshold_cap,
            )
            allowed_detectors = get_allowed_detectors(context.regime_hierarchy)
            if context.regime_hierarchy.primary == "compression" and primary_snapshot.regime_stability >= 0.67:
                confidence_cap_override = 99.0
            else:
                confidence_cap_override = context.regime_hierarchy.confidence_cap * 100.0

            self.shadow_engine.advance_pending(
                symbol=context.symbol,
                timeframe=primary_tf,
                df=context.datasets[primary_tf][1],
                trading_style=context.trading_style,
            )
            setup_book = detect_ranked_setups(
                snapshots=context.snapshots,
                style_cfg=context.config,
                patterns_by_timeframe=context.patterns_by_timeframe,
                allowed_detectors=allowed_detectors,
                regime_hierarchy=context.regime_hierarchy,
            )
            if context.data_quality:
                setup_book = filter_signals_by_data_quality(setup_book, context.data_quality)
                if context.data_quality.signals_blocked or context.data_quality.hard_block:
                    log_data_quality_event(context.data_quality)

            batch_id = str(uuid4())
            self._log_shadow_candidates(batch_id=batch_id, context=context, setup_book=setup_book)
            batch = build_analysis_batch(
                symbol=context.symbol,
                style=context.trading_style,
                snapshots=context.snapshots,
                style_cfg=context.config,
                patterns_by_timeframe=context.patterns_by_timeframe,
                setup_book=setup_book,
                batch_id=batch_id,
                allowed_detectors=allowed_detectors,
                regime_hierarchy=context.regime_hierarchy,
                confidence_cap_override=confidence_cap_override,
            )
            self.ranking.attach_pattern_matches(batch, context.snapshots, context.patterns_by_timeframe, primary_tf)
            self._apply_signal_adjustments(batch=batch, context=context)
            self._apply_position_decisions(batch=batch, context=context)
            context.kill_switch_decision = self._evaluate_kill_switch(context=context)
            if context.kill_switch_decision.halt_trading:
                self._apply_hold_reason(
                    batch,
                    reason_code="kill_switch_halt",
                    message="Kill switch halted trading for this cycle due to risk or data conditions.",
                )
            elif context.kill_switch_decision.require_manual_approval and batch.primary.direction in {"BUY", "SELL"}:
                batch.primary.context_tags.append("manual_approval_required")
                batch.primary.no_trade_reasons.append(
                    {
                        "code": "kill_switch_manual_approval",
                        "message": "Kill switch requires manual approval before auto-execution.",
                        "blocking": False,
                    }
                )

        summary = self.ranking.build_context_summary(context)

        batch.context_summary = summary.model_dump(mode="json")
        batch.engine_insight = self.ranking.build_engine_insight(
            context=context,
            batch=batch,
            setup_book=setup_book,
            context_summary=summary,
        )

        if publish:
            batch = await self.publisher.persist_and_broadcast(batch, context)

        return AnalysisBatchResponse(status="ok", data=batch, context=summary)
