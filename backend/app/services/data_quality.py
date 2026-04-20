from __future__ import annotations

from dataclasses import dataclass, field
from math import inf
from typing import TYPE_CHECKING

from app.services.database import db

if TYPE_CHECKING:
    from app.services.candle_source import CandleSourceResult
    from app.services.market_state import RankedSetupBook, SetupCandidate


SETUP_FRESHNESS_CLASS: dict[str, str] = {
    "micro_scalp_long": "live_only",
    "micro_scalp_short": "live_only",
    "breakout_continuation": "live_only",
    "breakdown_retest": "live_only",
    "pullback_continuation": "fresh_preferred",
    "lower_high_failure": "fresh_preferred",
    "range_reversion_long": "fresh_preferred",
    "range_reversion_short": "fresh_preferred",
    "exhaustion_reversal_long": "fresh_preferred",
    "exhaustion_reversal_short": "fresh_preferred",
    "demand_zone_reaction": "delayed_ok",
    "supply_zone_reaction": "delayed_ok",
}

FRESHNESS_RANK = {
    "live_only": 0,
    "fresh_preferred": 1,
    "delayed_ok": 2,
    "stale": 3,
}


@dataclass(frozen=True)
class DataQualityConfig:
    max_age_bars_by_class: dict[str, float] = field(
        default_factory=lambda: {
            "live_only": 3.0,
            "fresh_preferred": 5.0,
            "delayed_ok": 10.0,
        }
    )
    hard_block_max_bars: float = 5.0

    def freshness_class_for_setup(self, setup_type: str) -> str:
        return SETUP_FRESHNESS_CLASS.get(setup_type, "fresh_preferred")


@dataclass
class DataQualityContext:
    symbol: str
    timeframe: str
    source: str
    is_live: bool
    age_seconds: float
    max_expected_age_seconds: float
    age_bars: float
    freshness_passed: bool
    allowed_strategy_class: str
    notes: list[str] = field(default_factory=list)
    signals_blocked: int = 0

    @property
    def hard_block(self) -> bool:
        return not self.freshness_passed


def _age_bars(result: CandleSourceResult) -> float:
    age_seconds = float(result.age_seconds or inf)
    max_expected_age_seconds = float(result.max_expected_age_seconds or 0.0)
    if max_expected_age_seconds <= 0:
        max_expected_age_seconds = 60.0
    if age_seconds == inf or age_seconds != age_seconds:
        age_seconds = 60.0
    age_bars = age_seconds / max_expected_age_seconds
    if age_bars > 1000 or age_bars != age_bars:
        return 999.0
    return age_bars


def _allowed_strategy_class(age_bars: float, config: DataQualityConfig) -> str:
    if age_bars <= config.max_age_bars_by_class["live_only"]:
        return "live_only"
    if age_bars <= config.max_age_bars_by_class["fresh_preferred"]:
        return "fresh_preferred"
    if age_bars <= config.max_age_bars_by_class["delayed_ok"]:
        return "delayed_ok"
    return "stale"


def get_data_quality_context(
    *,
    symbol: str,
    timeframe: str,
    source_result: CandleSourceResult,
    config: DataQualityConfig | None = None,
) -> DataQualityContext:
    config = config or DataQualityConfig()
    age_seconds = float(source_result.age_seconds) if source_result.age_seconds is not None else 999.0
    if age_seconds != age_seconds or age_seconds == inf:  # Handle NaN or inf
        age_seconds = 999.0
    age_bars = _age_bars(source_result)
    allowed_strategy_class = _allowed_strategy_class(age_bars, config)
    freshness_passed = bool(source_result.freshness_ok) and age_bars <= config.hard_block_max_bars
    notes = list(source_result.notes)
    if not freshness_passed:
        notes.append("stale_primary_data")
    elif allowed_strategy_class != "live_only":
        notes.append(f"freshness_class:{allowed_strategy_class}")

    return DataQualityContext(
        symbol=symbol,
        timeframe=timeframe,
        source=source_result.source,
        is_live=source_result.is_live,
        age_seconds=age_seconds,
        max_expected_age_seconds=float(source_result.max_expected_age_seconds or 0.0),
        age_bars=age_bars,
        freshness_passed=freshness_passed,
        allowed_strategy_class=allowed_strategy_class,
        notes=notes,
    )


def _is_setup_allowed(setup_type: str, context: DataQualityContext, config: DataQualityConfig) -> bool:
    required_class = config.freshness_class_for_setup(setup_type)
    return FRESHNESS_RANK[required_class] >= FRESHNESS_RANK[context.allowed_strategy_class]


def filter_signals_by_data_quality(
    setup_book: RankedSetupBook,
    context: DataQualityContext,
    config: DataQualityConfig | None = None,
) -> RankedSetupBook:
    from app.services.market_state import RankedSetupBook

    config = config or DataQualityConfig()
    selected: list[SetupCandidate] = []
    rejected = list(setup_book.rejected)

    for candidate in setup_book.selected:
        if context.hard_block or not _is_setup_allowed(candidate.setup_type, context, config):
            candidate.is_rejected = True
            candidate.no_trade_reasons.append(
                {
                    "code": "data_quality_block",
                    "message": (
                        f"{candidate.setup_type.replace('_', ' ')} requires "
                        f"{config.freshness_class_for_setup(candidate.setup_type)} data, "
                        f"but current dataset is {context.allowed_strategy_class} "
                        f"at {context.age_bars:.2f} bars old."
                    ),
                    "blocking": True,
                }
            )
            candidate.context_tags.append(f"blocked:{context.allowed_strategy_class}")
            rejected.append(candidate)
            context.signals_blocked += 1
            continue
        selected.append(candidate)

    return RankedSetupBook(selected=selected, rejected=rejected)


def log_data_quality_event(context: DataQualityContext) -> None:
    if not db.is_enabled():
        return
    try:
        db.log_data_quality_event(
            symbol=context.symbol,
            timeframe=context.timeframe,
            source=context.source,
            age_seconds=context.age_seconds,
            is_fresh=context.freshness_passed,
            allowed_strategy_class=context.allowed_strategy_class,
            signals_blocked=context.signals_blocked,
        )
    except Exception:
        # Best-effort only: data-quality logging must never block analysis.
        return
