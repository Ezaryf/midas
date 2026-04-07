/**
 * Canonical TradeSignal type — matches the backend snake_case schema.
 * The frontend mock data uses camelCase; adapters handle the bridge.
 */
export interface TradeSignal {
  id?: string;
<<<<<<< HEAD
  symbol?: string;
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
  timestamp?: string;
  direction: "BUY" | "SELL" | "HOLD";
  entry_price: number;
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  confidence: number;
  reasoning: string;
  trading_style: "Scalper" | "Intraday" | "Swing";
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

/** Adapts the mock-data camelCase Signal to the canonical TradeSignal */
export function adaptMockSignal(s: {
  id?: string;
<<<<<<< HEAD
  symbol?: string;
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
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
<<<<<<< HEAD
    symbol: s.symbol,
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
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
};
