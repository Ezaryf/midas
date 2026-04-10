from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.signal import AnalysisBatch, TradeSignal


class SourceQuality(BaseModel):
    symbol_match: bool = True
    tick_fresh: bool = False
    source: str = "unknown"
    is_live: bool = False
    confidence_cap: float = 0
    age_seconds: float | None = None
    freshness_passed: bool | None = None
    allowed_strategy_class: str | None = None
    notes: list[str] = Field(default_factory=list)


class CandidateEvidence(BaseModel):
    regime_alignment: float = 0
    structure_confirmation: float = 0
    actionability: float = 0
    confluence: float = 0
    invalidation_quality: float = 0
    source_quality: float = 0
    conflict_penalty: float = 0
    pattern_boost: float = 0
    rr: float = 0
    proximity: float = 0


class NoTradeReason(BaseModel):
    code: str
    message: str
    blocking: bool = True


class TickSnapshot(BaseModel):
    symbol: str | None = None
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    time: datetime | None = None
    received_at: datetime | None = None


class TimeframeDatasetSummary(BaseModel):
    timeframe: str
    source: str
    is_live: bool
    candles: int
    source_quality: SourceQuality


class ExecutionConstraints(BaseModel):
    auto_execute_confidence: float
    rr_min: float
    rr_target: float
    max_backups: int


class AnalysisContextSummary(BaseModel):
    symbol: str
    trading_style: Literal["Scalper", "Intraday", "Swing"]
    current_price: float
    tick: TickSnapshot | None = None
    datasets: list[TimeframeDatasetSummary] = Field(default_factory=list)
    session_active: bool = True
    news_blocked: bool = False
    risk_blocked: bool = False
    primary_regime_stability: float | None = None
    primary_data_age_seconds: float | None = None
    primary_freshness_passed: bool | None = None
    kill_switch: dict[str, Any] = Field(default_factory=dict)
    constraints: ExecutionConstraints
    generated_at: datetime


class AnalysisBatchResponse(BaseModel):
    status: Literal["ok"] = "ok"
    data: AnalysisBatch
    context: AnalysisContextSummary


class ExecutionResultResponse(BaseModel):
    status: Literal["ok", "warning", "error"]
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class RiskCheckResponse(BaseModel):
    status: Literal["ok", "warning", "error"] = "ok"
    allowed: bool
    reason: str
    symbol: str | None = None
    direction: str | None = None
    volume: float | None = None
    price: float | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "disconnected", "error"]
    mt5_connected: bool
    bridge_count: int
    latest_price: float | None = None
    pending_signals: int = 0
    database_enabled: bool = False
    runtime_state: dict[str, Any] = Field(default_factory=dict)
    message: str


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
