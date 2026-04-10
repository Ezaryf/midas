import { z } from "zod";
import type {
  AnalysisBatch,
  AnalysisContextSummary,
  CalendarEvent,
  CandidateInsight,
  DecisionGateStatus,
  EngineInsight,
  MarketPhaseSummary,
  MidasConfig,
  NewsItem,
  PatternInsight,
  TradeSignal,
} from "@/lib/types";
import type { Position } from "@/hooks/usePositions";
import type { PerformanceStats } from "@/hooks/usePerformance";

export const tradeSignalSchema: z.ZodType<TradeSignal> = z.object({
  id: z.string().optional(),
  signal_id: z.string().optional(),
  symbol: z.string().optional(),
  analysis_batch_id: z.string().optional(),
  timestamp: z.string().optional(),
  direction: z.enum(["BUY", "SELL", "HOLD"]),
  entry_price: z.number(),
  stop_loss: z.number(),
  take_profit_1: z.number(),
  take_profit_2: z.number(),
  confidence: z.number(),
  reasoning: z.string(),
  trading_style: z.enum(["Scalper", "Intraday", "Swing"]),
  setup_type: z.string().optional(),
  market_regime: z.string().optional(),
  score: z.number().optional(),
  rank: z.number().optional(),
  is_primary: z.boolean().optional(),
  entry_window_low: z.number().optional(),
  entry_window_high: z.number().optional(),
  context_tags: z.array(z.string()).optional(),
  source: z.string().optional(),
  auto_execute: z.boolean().optional(),
  status: z.enum(["PENDING", "ACTIVE", "HIT_TP1", "HIT_TP2", "STOPPED", "EXPIRED"]).optional(),
  outcome: z.number().optional(),
  patterns: z.array(z.object({
    type: z.string(),
    confidence: z.number(),
    description: z.string(),
  })).optional(),
  evidence: z.record(z.string(), z.number()).optional(),
  no_trade_reasons: z.array(z.object({
    code: z.string(),
    message: z.string(),
    blocking: z.boolean(),
  })).optional(),
});

export const patternInsightSchema: z.ZodType<PatternInsight> = z.object({
  type: z.string(),
  family: z.enum(["chart", "candlestick"]),
  timeframe: z.string(),
  direction: z.enum(["BUY", "SELL"]),
  confidence: z.number(),
  description: z.string(),
  relation: z.enum(["support", "conflict", "neutral"]),
  entry_price: z.number().nullable().optional(),
});

export const candidateInsightSchema: z.ZodType<CandidateInsight> = z.object({
  setup_type: z.string(),
  direction: z.enum(["BUY", "SELL", "HOLD"]),
  status: z.enum(["selected", "backup", "rejected"]),
  entry_price: z.number(),
  stop_loss: z.number(),
  take_profit_1: z.number(),
  take_profit_2: z.number(),
  score: z.number(),
  rr: z.number(),
  evidence: z.record(z.string(), z.number()).default({}),
  blocker_reasons: z.array(z.object({
    code: z.string(),
    message: z.string(),
    blocking: z.boolean(),
  })).default([]),
  context_tags: z.array(z.string()).default([]),
  linked_patterns: z.array(patternInsightSchema).default([]),
  reasoning: z.string(),
});

export const decisionGateStatusSchema: z.ZodType<DecisionGateStatus> = z.object({
  code: z.string(),
  label: z.string(),
  passed: z.boolean(),
  detail: z.string(),
  blocking: z.boolean(),
});

export const marketPhaseSummarySchema: z.ZodType<MarketPhaseSummary> = z.object({
  key: z.string(),
  label: z.string(),
  description: z.string(),
});

export const analysisContextSummarySchema: z.ZodType<AnalysisContextSummary> = z.object({
  symbol: z.string(),
  trading_style: z.enum(["Scalper", "Intraday", "Swing"]),
  current_price: z.number(),
  tick: z.object({
    symbol: z.string().nullable().optional(),
    bid: z.number().nullable().optional(),
    ask: z.number().nullable().optional(),
    spread: z.number().nullable().optional(),
    time: z.string().nullable().optional(),
    received_at: z.string().nullable().optional(),
  }).nullable().optional(),
  datasets: z.array(z.object({
    timeframe: z.string(),
    source: z.string(),
    is_live: z.boolean(),
    candles: z.number(),
    source_quality: z.object({
      symbol_match: z.boolean(),
      tick_fresh: z.boolean(),
      source: z.string(),
      is_live: z.boolean(),
      confidence_cap: z.number(),
      notes: z.array(z.string()).default([]),
    }),
  })).default([]),
  session_active: z.boolean(),
  news_blocked: z.boolean(),
  risk_blocked: z.boolean(),
  constraints: z.object({
    auto_execute_confidence: z.number(),
    rr_min: z.number(),
    rr_target: z.number(),
    max_backups: z.number(),
  }),
  generated_at: z.string(),
});

export const engineInsightSchema: z.ZodType<EngineInsight> = z.object({
  phase: marketPhaseSummarySchema,
  summary: z.string(),
  candidates: z.array(candidateInsightSchema).default([]),
  patterns: z.array(patternInsightSchema).default([]),
  decision_gates: z.array(decisionGateStatusSchema).default([]),
});

export const analysisBatchSchema: z.ZodType<AnalysisBatch> = z.object({
  analysis_batch_id: z.string(),
  symbol: z.string(),
  trading_style: z.enum(["Scalper", "Intraday", "Swing"]),
  evaluated_at: z.string(),
  market_regime: z.string(),
  regime_summary: z.string(),
  source: z.string(),
  source_is_live: z.boolean(),
  context_summary: analysisContextSummarySchema.optional(),
  engine_insight: engineInsightSchema.nullable().optional(),
  primary: tradeSignalSchema,
  backups: z.array(tradeSignalSchema),
});

export const candleSchema = z.object({
  time: z.number(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number().optional(),
});

export const candlesResponseSchema = z.object({
  candles: z.array(candleSchema).default([]),
});

export const newsItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  source: z.string(),
  sentiment: z.enum(["bullish", "bearish", "neutral"]),
  impact: z.enum(["high", "medium", "low"]),
  publishedAt: z.string(),
  summary: z.string(),
  url: z.string().optional(),
}).transform((value): NewsItem => ({
  ...value,
  publishedAt: new Date(value.publishedAt),
}));

export const newsResponseSchema = z.object({
  items: z.array(newsItemSchema).default([]),
});

export const calendarEventSchema = z.object({
  id: z.string(),
  title: z.string(),
  country: z.string(),
  impact: z.enum(["high", "medium", "low"]),
  forecast: z.string(),
  previous: z.string(),
  actual: z.string().optional(),
  scheduledAt: z.string(),
}).transform((value): CalendarEvent => ({
  ...value,
  scheduledAt: new Date(value.scheduledAt),
}));

export const calendarResponseSchema = z.object({
  events: z.array(calendarEventSchema).default([]),
});

export const positionSchema: z.ZodType<Position> = z.object({
  ticket: z.number(),
  symbol: z.string(),
  type: z.string(),
  volume: z.number(),
  open_price: z.number(),
  current_price: z.number(),
  sl: z.number(),
  tp: z.number(),
  profit: z.number(),
  swap: z.number(),
  commission: z.number(),
  open_time: z.string(),
  comment: z.string(),
});

export const positionsResponseSchema = z.object({
  positions: z.array(positionSchema).default([]),
});

export const backendHealthSchema = z.object({
  status: z.string(),
  latest_price: z.number().nullable().optional(),
}).passthrough();

export const performanceStatsSchema: z.ZodType<PerformanceStats> = z.object({
  totalSignals: z.number(),
  wins: z.number(),
  losses: z.number(),
  winRate: z.number(),
  grossProfit: z.number(),
  grossLoss: z.number(),
  totalPnl: z.number(),
  todayPnl: z.number(),
  weekPnl: z.number(),
  profitFactor: z.number(),
});

export const signalHistoryResponseSchema = z.object({
  signals: z.array(tradeSignalSchema).default([]),
});

export const performanceResponseSchema = z.object({
  stats: performanceStatsSchema,
});

export const persistedConfigSchema: z.ZodType<MidasConfig> = z.object({
  mt5Account: z.string(),
  mt5Server: z.string(),
  mt5Password: z.string(),
  autoTrade: z.boolean(),
  aiProvider: z.enum(["openai", "claude", "gemini", "grok", "groq"]),
  apiKey: z.string(),
  tradingStyle: z.enum(["scalper", "intraday", "swing"]),
  maxRiskPercent: z.number(),
  dailyLossLimit: z.number(),
  newsBlackoutMinutes: z.number(),
  autoExecuteConfidence: z.number(),
  maxDailyTrades: z.number(),
  analysisIntervalSeconds: z.number(),
  positionCooldownSeconds: z.number(),
  maxConcurrentSignals: z.number(),
  maxConcurrentPositions: z.number(),
  enableKillSwitch: z.boolean(),
});
