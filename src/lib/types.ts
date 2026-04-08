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
  // UI-only status (not from backend)
  status?: "PENDING" | "ACTIVE" | "HIT_TP1" | "HIT_TP2" | "STOPPED" | "EXPIRED";
  outcome?: number;
  // Pattern detection results
  patterns?: Array<{
    type: string;
    confidence: number;
    description: string;
  }>;
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
  notes: string[];
  symbol: string;
  trading_style: string;
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
  maxConcurrentSignals: number;
  maxConcurrentPositions: number;
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
  maxConcurrentSignals: 3,
  maxConcurrentPositions: 3,
};
