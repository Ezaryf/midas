export const TRADING_STYLES = {
  SCALPER: "Scalper",
  INTRADAY: "Intraday",
  SWING: "Swing",
} as const;

export const DIRECTION = {
  BUY: "BUY",
  SELL: "SELL",
  HOLD: "HOLD",
} as const;

export const SIGNAL_STATUS = {
  PENDING: "PENDING",
  ACTIVE: "ACTIVE",
  HIT_TP1: "HIT_TP1",
  HIT_TP2: "HIT_TP2",
  STOPPED: "STOPPED",
  EXPIRED: "EXPIRED",
} as const;

export const EXECUTION_MODE = {
  NORMAL: "normal",
  FORCED: "forced",
} as const;

export const NEWS_SENTIMENT = {
  BULLISH: "bullish",
  BEARISH: "bearish",
  NEUTRAL: "neutral",
} as const;

export const NEWS_IMPACT = {
  HIGH: "high",
  MEDIUM: "medium",
  LOW: "low",
} as const;

export const SERVICE_STATUS = {
  IDLE: "idle",
  CHECKING: "checking",
  CONNECTED: "connected",
  ERROR: "error",
} as const;

export const DEFAULT_SYMBOL = "XAUUSD";
export const DEFAULT_CALIBRATION_FACTOR = 1.0;
export const MAX_SIGNAL_HISTORY = 100;
export const DEFAULT_RETRY_DELAY = 5000;
export const DEFAULT_QUERY_STALE_TIME = 15_000;
export const DEFAULT_QUERY_GC_TIME = 5 * 60_000;