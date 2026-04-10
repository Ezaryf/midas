/**
 * Canonical TradeSignal type — matches the backend snake_case schema.
 * The frontend mock data uses camelCase; adapters handle the bridge.
 */
export interface TradeSignal {
  id?: string;
  signal_id?: string;
  symbol?: string;
  analysis_batch_id?: string;
  timestamp?: string;
  direction: "BUY" | "SELL" | "HOLD";
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  confidence: number;
  reasoning: string;
  trading_style: "Scalper" | "Intraday" | "Swing";
  setup_type?: string;
  market_regime?: string;
  score?: number;
  rank?: number;
  is_primary?: boolean;
  entry_window_low?: number;
  entry_window_high?: number;
  context_tags?: string[];
  source?: string;
  auto_execute?: boolean;
  execution_mode?: "normal" | "forced";
  forced_from_hold?: boolean;
  bypassed_blockers?: string[];
  source_candidate_stage?: "filtered" | "raw";
  // UI-only status (not from backend)
  status?: "PENDING" | "ACTIVE" | "HIT_TP1" | "HIT_TP2" | "STOPPED" | "EXPIRED";
  outcome?: number;
  // Pattern detection results
  patterns?: Array<{
    type: string;
    confidence: number;
    description: string;
  }>;
  evidence?: Record<string, number>;
  no_trade_reasons?: Array<{
    code: string;
    message: string;
    blocking: boolean;
  }>;
}

export interface PatternInsight {
  type: string;
  family: "chart" | "candlestick";
  timeframe: string;
  direction: "BUY" | "SELL";
  confidence: number;
  description: string;
  relation: "support" | "conflict" | "neutral";
  entry_price?: number | null;
}

export interface CandidateInsight {
  setup_type: string;
  direction: "BUY" | "SELL" | "HOLD";
  status: "selected" | "backup" | "rejected";
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  score: number;
  rr: number;
  evidence: Record<string, number>;
  blocker_reasons: Array<{
    code: string;
    message: string;
    blocking: boolean;
  }>;
  context_tags: string[];
  linked_patterns: PatternInsight[];
  reasoning: string;
}

export interface DecisionGateStatus {
  code: string;
  label: string;
  passed: boolean;
  detail: string;
  blocking: boolean;
}

export interface MarketPhaseSummary {
  key: string;
  label: string;
  description: string;
}

export interface SourceQuality {
  symbol_match: boolean;
  tick_fresh: boolean;
  source: string;
  is_live: boolean;
  confidence_cap: number;
  notes: string[];
}

export interface TimeframeDatasetSummary {
  timeframe: string;
  source: string;
  is_live: boolean;
  candles: number;
  source_quality: SourceQuality;
}

export interface TickSnapshot {
  symbol?: string | null;
  bid?: number | null;
  ask?: number | null;
  spread?: number | null;
  time?: string | null;
  received_at?: string | null;
}

export interface AnalysisContextSummary {
  symbol: string;
  trading_style: "Scalper" | "Intraday" | "Swing";
  current_price: number;
  tick?: TickSnapshot | null;
  datasets: TimeframeDatasetSummary[];
  session_active: boolean;
  news_blocked: boolean;
  risk_blocked: boolean;
  constraints: {
    auto_execute_confidence: number;
    rr_min: number;
    rr_target: number;
    max_backups: number;
  };
  generated_at: string;
}

export interface EngineInsight {
  phase: MarketPhaseSummary;
  summary: string;
  candidates: CandidateInsight[];
  patterns: PatternInsight[];
  decision_gates: DecisionGateStatus[];
}

export interface AnalysisBatch {
  analysis_batch_id: string;
  symbol: string;
  trading_style: "Scalper" | "Intraday" | "Swing";
  evaluated_at: string;
  market_regime: string;
  regime_summary: string;
  source: string;
  source_is_live: boolean;
  context_summary?: AnalysisContextSummary;
  engine_insight?: EngineInsight | null;
  primary: TradeSignal;
  backups: TradeSignal[];
}

export interface MarketState {
  timeframe: string;
  source: string;
  is_live: boolean;
  current_price: number;
  atr: number;
  avg_body: number;
  body_strength: number;
  upper_wick: number;
  lower_wick: number;
  close_location: number;
  relative_volume: number;
  efficiency_ratio: number;
  compression_ratio: number;
  ema_slope: number;
  range_high: number;
  range_low: number;
  range_width: number;
  boundary_touches_high: number;
  boundary_touches_low: number;
  recent_high: number;
  recent_low: number;
  support: number;
  resistance: number;
  recent_minor_high: number;
  prior_minor_high: number;
  recent_minor_low: number;
  prior_minor_low: number;
  swings: Array<{ type: "high" | "low"; index: number; price: number }>;
  regime: string;
  regime_confidence: number;
  phase_key?: string | null;
  phase_label?: string | null;
  phase_description?: string | null;
  notes: string[];
  symbol: string;
  trading_style: string;
  context_summary?: AnalysisContextSummary;
}

/** Adapts the mock-data camelCase Signal to the canonical TradeSignal */
export function adaptMockSignal(s: {
  id?: string;
  symbol?: string;
  direction: "BUY" | "SELL";
  entryPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  confidence: number;
  reasoning: string;
  tradingStyle: string;
  status?: string;
  outcome?: number;
  createdAt?: Date;
}): TradeSignal {
  return {
    id: s.id,
    symbol: s.symbol,
    timestamp: s.createdAt?.toISOString(),
    direction: s.direction,
    entry_price: s.entryPrice,
    stop_loss: s.stopLoss,
    take_profit_1: s.takeProfit1,
    take_profit_2: s.takeProfit2,
    confidence: s.confidence,
    reasoning: s.reasoning,
    trading_style: (s.tradingStyle.charAt(0).toUpperCase() + s.tradingStyle.slice(1)) as TradeSignal["trading_style"],
    status: s.status as TradeSignal["status"],
    outcome: s.outcome,
  };
}

export interface NewsItem {
  id: string;
  title: string;
  source: string;
  sentiment: "bullish" | "bearish" | "neutral";
  impact: "high" | "medium" | "low";
  publishedAt: Date;
  summary: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  country: string;
  impact: "high" | "medium" | "low";
  forecast: string;
  previous: string;
  actual?: string;
  scheduledAt: Date;
}

export interface MidasConfig {
  mt5Account: string;
  mt5Server: string;
  mt5Password: string;
  autoTrade: boolean;
  aiProvider: "openai" | "claude" | "gemini" | "grok" | "groq";
  apiKey: string;
  tradingStyle: "scalper" | "intraday" | "swing";
  maxRiskPercent: number;
  dailyLossLimit: number;
  newsBlackoutMinutes: number;
  autoExecuteConfidence: number;
  maxDailyTrades: number;
  analysisIntervalSeconds: number;
  positionCooldownSeconds: number;
  maxConcurrentSignals: number;
  maxConcurrentPositions: number;
  enableKillSwitch: boolean;
  minLotSize: number;
  maxLotSize: number;
  minStopDistancePoints: number;
  partialCloseEnabled: boolean;
  partialClosePercent: number;
  breakevenEnabled: boolean;
  breakevenBufferPips: number;
  trailingStopEnabled: boolean;
  trailingStopDistancePips: number;
  trailingStopStepPips: number;
  timeExitEnabled: boolean;
  exitBeforeNewsMinutes: number;
  exitBeforeWeekendHours: number;
}

export const DEFAULT_CONFIG: MidasConfig = {
  mt5Account: "",
  mt5Server: "",
  mt5Password: "",
  autoTrade: false,
  aiProvider: "openai",
  apiKey: "",
  tradingStyle: "intraday",
  maxRiskPercent: 1.0,
  dailyLossLimit: 500,
  newsBlackoutMinutes: 30,
  autoExecuteConfidence: 10,
  maxDailyTrades: 10,
  analysisIntervalSeconds: 10,
  positionCooldownSeconds: 30,
  maxConcurrentSignals: 3,
  maxConcurrentPositions: 3,
  enableKillSwitch: true,
  minLotSize: 0.01,
  maxLotSize: 1.0,
  minStopDistancePoints: 30,
  partialCloseEnabled: true,
  partialClosePercent: 50,
  breakevenEnabled: true,
  breakevenBufferPips: 5,
  trailingStopEnabled: true,
  trailingStopDistancePips: 50,
  trailingStopStepPips: 10,
  timeExitEnabled: true,
  exitBeforeNewsMinutes: 15,
  exitBeforeWeekendHours: 2,
};
