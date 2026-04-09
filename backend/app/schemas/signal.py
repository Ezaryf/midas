from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PatternInsight(BaseModel):
    type: str
    family: Literal["chart", "candlestick"]
    timeframe: str
    direction: Literal["BUY", "SELL"]
    confidence: float = Field(ge=0, le=100)
    description: str
    relation: Literal["support", "conflict", "neutral"] = "neutral"
    entry_price: float | None = None


class CandidateInsight(BaseModel):
    setup_type: str
    direction: Literal["BUY", "SELL", "HOLD"]
    status: Literal["selected", "backup", "rejected"]
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    score: float = Field(ge=0, le=100)
    rr: float = Field(ge=0)
    evidence: dict[str, float] = Field(default_factory=dict)
    blocker_reasons: list[dict[str, str | bool]] = Field(default_factory=list)
    context_tags: list[str] = Field(default_factory=list)
    linked_patterns: list[PatternInsight] = Field(default_factory=list)
    reasoning: str = ""


class DecisionGateStatus(BaseModel):
    code: str
    label: str
    passed: bool
    detail: str
    blocking: bool = False


class MarketPhaseSummary(BaseModel):
    key: str
    label: str
    description: str


class EngineInsight(BaseModel):
    phase: MarketPhaseSummary
    summary: str
    candidates: list[CandidateInsight] = Field(default_factory=list)
    patterns: list[PatternInsight] = Field(default_factory=list)
    decision_gates: list[DecisionGateStatus] = Field(default_factory=list)


class TradeSignal(BaseModel):
    id: str | None = None
    signal_id: str | None = None
    symbol: str | None = None
    analysis_batch_id: str | None = None
    timestamp: datetime | None = None
    direction: Literal["BUY", "SELL", "HOLD"] = Field(
        ..., description="The directional bias of the trade. If HOLD, no trade is recommended."
    )
    entry_price: float = Field(
        ..., description="The optimal entry price for the trade."
    )
    stop_loss: float = Field(
        ..., description="The stop loss price to invalidate the setup. Must be placed logically behind structure."
    )
    take_profit_1: float = Field(
        ..., description="The first conservative take profit target (TP1)."
    )
    take_profit_2: float = Field(
        ..., description="The secondary, more aggressive take profit target (TP2)."
    )
    confidence: float = Field(
        ..., description="A score from 0 to 100 representing the model's confidence in this setup.", ge=0, le=100
    )
    reasoning: str = Field(
        ..., description="A concise, two-sentence explanation of the trade rationale based on technicals and fundamentals."
    )
    trading_style: Literal["Scalper", "Intraday", "Swing"] = Field(
        ..., description="The inferred holding period/style this setup is built for."
    )
    setup_type: str = Field(
        default="manual",
        description="Deterministic setup classification produced by the market-state engine.",
    )
    market_regime: str = Field(
        default="neutral",
        description="The dominant detected market regime that contextualizes the trade.",
    )
    score: float = Field(
        default=0,
        ge=0,
        le=100,
        description="Composite quality score used for ranking candidates.",
    )
    rank: int = Field(
        default=1,
        ge=1,
        description="Rank within the analysis batch. 1 is the primary executable setup.",
    )
    is_primary: bool = Field(
        default=True,
        description="Whether this setup is the executable primary signal for the current batch.",
    )
    entry_window_low: float = Field(
        default=0,
        description="Lower bound of the preferred execution window.",
    )
    entry_window_high: float = Field(
        default=0,
        description="Upper bound of the preferred execution window.",
    )
    context_tags: list[str] = Field(
        default_factory=list,
        description="Compact context tags that explain the setup's structural drivers.",
    )
    patterns: list[dict[str, str | float]] = Field(
        default_factory=list,
        description="Supporting confirmation patterns attached for UI visibility.",
    )
    source: str | None = Field(
        default=None,
        description="Data source that produced this setup, e.g. mt5 or yahoo.",
    )
    evidence: dict[str, float] = Field(
        default_factory=dict,
        description="Structured evidence scores used by the ranking engine.",
    )
    no_trade_reasons: list[dict[str, str | bool]] = Field(
        default_factory=list,
        description="Explicit reasons explaining why the engine returned HOLD or rejected execution.",
    )

    # ── Position-Aware Decision Fields ────────────────────────────────────────
    position_action: str | None = Field(
        default=None,
        description="Action decided by the PositionManager: open/close/reverse/reduce/ignore/scale_in.",
    )
    position_action_reason: str | None = Field(
        default=None,
        description="Human-readable explanation of why the PositionManager chose this action.",
    )
    is_duplicate: bool = Field(
        default=False,
        description="True if this signal was suppressed as a duplicate within the cooldown window.",
    )
    calibrated_confidence: float | None = Field(
        default=None,
        description="Post-calibration confidence before any final execution gating.",
    )
    confidence_source: str | None = Field(
        default=None,
        description="Origin of the current confidence value: raw/calibrated/execution_adjusted.",
    )


class AnalysisBatch(BaseModel):
    analysis_batch_id: str
    symbol: str
    trading_style: Literal["Scalper", "Intraday", "Swing"]
    evaluated_at: datetime
    market_regime: str
    regime_summary: str
    source: str
    source_is_live: bool
    context_summary: dict = Field(default_factory=dict)
    engine_insight: EngineInsight | None = None
    primary: TradeSignal
    backups: list[TradeSignal] = Field(default_factory=list)
