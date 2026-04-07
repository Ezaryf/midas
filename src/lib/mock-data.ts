// ============================================
// MOCK DATA for Midas Dashboard Development
// Simulates all data the real backend will provide
// ============================================

export interface Signal {
  id: string;
  direction: "BUY" | "SELL";
  entryPrice: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  confidence: number;
  reasoning: string;
  tradingStyle: "intraday" | "swing" | "scalper";
  status: "PENDING" | "ACTIVE" | "HIT_TP1" | "HIT_TP2" | "STOPPED" | "EXPIRED";
  outcome?: number;
  createdAt: Date;
}

export interface CandleData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
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

// --- Active Signal (mock fallback — replaced by real AI signal) ---
export const mockActiveSignal: Signal = {
  id: "sig-001",
  direction: "BUY",
  entryPrice: 4627.00,
  stopLoss: 4600.00,
  takeProfit1: 4660.00,
  takeProfit2: 4700.00,
  confidence: 78,
  reasoning:
    "Bullish structure intact above 4600 support. RSI recovering from oversold. USD weakening on dovish Fed tone. Targeting previous swing high at 4660.",
  tradingStyle: "intraday",
  status: "ACTIVE",
  createdAt: new Date(Date.now() - 15 * 60000),
};

// --- Signal History ---
export const mockSignalHistory: Signal[] = [
  {
    id: "sig-010",
    direction: "BUY",
    entryPrice: 3105.20,
    stopLoss: 3095.00,
    takeProfit1: 3120.00,
    takeProfit2: 3135.00,
    confidence: 82,
    reasoning: "Double bottom formation at key support level.",
    tradingStyle: "intraday",
    status: "HIT_TP2",
    outcome: 29.80,
    createdAt: new Date(Date.now() - 2 * 3600000),
  },
  {
    id: "sig-009",
    direction: "SELL",
    entryPrice: 3142.80,
    stopLoss: 3152.00,
    takeProfit1: 3128.00,
    takeProfit2: 3115.00,
    confidence: 71,
    reasoning: "Bearish divergence on RSI with price at resistance.",
    tradingStyle: "swing",
    status: "HIT_TP1",
    outcome: 14.80,
    createdAt: new Date(Date.now() - 5 * 3600000),
  },
  {
    id: "sig-008",
    direction: "BUY",
    entryPrice: 3098.00,
    stopLoss: 3088.50,
    takeProfit1: 3112.00,
    takeProfit2: 3125.00,
    confidence: 65,
    reasoning: "Support bounce with bullish momentum.",
    tradingStyle: "scalper",
    status: "STOPPED",
    outcome: -9.50,
    createdAt: new Date(Date.now() - 8 * 3600000),
  },
  {
    id: "sig-007",
    direction: "SELL",
    entryPrice: 3155.40,
    stopLoss: 3165.00,
    takeProfit1: 3140.00,
    takeProfit2: 3125.00,
    confidence: 85,
    reasoning: "Triple top pattern confirmed with high-impact USD data.",
    tradingStyle: "intraday",
    status: "HIT_TP2",
    outcome: 30.40,
    createdAt: new Date(Date.now() - 12 * 3600000),
  },
  {
    id: "sig-006",
    direction: "BUY",
    entryPrice: 3088.00,
    stopLoss: 3078.00,
    takeProfit1: 3102.00,
    takeProfit2: 3115.00,
    confidence: 74,
    reasoning: "Morning star candle at weekly support zone.",
    tradingStyle: "swing",
    status: "HIT_TP1",
    outcome: 14.00,
    createdAt: new Date(Date.now() - 18 * 3600000),
  },
  {
    id: "sig-005",
    direction: "SELL",
    entryPrice: 3130.20,
    stopLoss: 3140.00,
    takeProfit1: 3115.00,
    takeProfit2: 3100.00,
    confidence: 68,
    reasoning: "Evening star formation near resistance with NFP release.",
    tradingStyle: "intraday",
    status: "HIT_TP1",
    outcome: 15.20,
    createdAt: new Date(Date.now() - 24 * 3600000),
  },
  {
    id: "sig-004",
    direction: "BUY",
    entryPrice: 3070.50,
    stopLoss: 3060.00,
    takeProfit1: 3085.00,
    takeProfit2: 3100.00,
    confidence: 91,
    reasoning: "Strong demand zone confluence with 200 SMA on H1.",
    tradingStyle: "swing",
    status: "HIT_TP2",
    outcome: 29.50,
    createdAt: new Date(Date.now() - 36 * 3600000),
  },
];

// --- News Items ---
export const mockNewsItems: NewsItem[] = [
  {
    id: "n1",
    title: "Fed Minutes Signal Potential Rate Cut in Q3 2026",
    source: "Reuters",
    sentiment: "bullish",
    impact: "high",
    publishedAt: new Date(Date.now() - 30 * 60000),
    summary: "FOMC minutes revealed growing consensus for a rate reduction, weakening USD outlook.",
  },
  {
    id: "n2",
    title: "China Central Bank Increases Gold Reserves for 8th Month",
    source: "Bloomberg",
    sentiment: "bullish",
    impact: "high",
    publishedAt: new Date(Date.now() - 2 * 3600000),
    summary: "PBOC added 15 tonnes of gold in March, continuing de-dollarization trend.",
  },
  {
    id: "n3",
    title: "US CPI Comes in Higher Than Expected at 3.2%",
    source: "CNBC",
    sentiment: "bearish",
    impact: "high",
    publishedAt: new Date(Date.now() - 4 * 3600000),
    summary: "Higher-than-expected inflation may delay Fed rate cuts, boosting USD short-term.",
  },
  {
    id: "n4",
    title: "Geopolitical Tensions Mount in Middle East",
    source: "Al Jazeera",
    sentiment: "bullish",
    impact: "medium",
    publishedAt: new Date(Date.now() - 6 * 3600000),
    summary: "Escalating regional tensions drive safe-haven demand for gold.",
  },
  {
    id: "n5",
    title: "Dollar Index Retreats to 102.5 After Weak Jobs Data",
    source: "FXStreet",
    sentiment: "bullish",
    impact: "medium",
    publishedAt: new Date(Date.now() - 8 * 3600000),
    summary: "DXY falls 0.4% as non-farm payrolls miss expectations, supporting gold prices.",
  },
];

// --- Calendar Events ---
export const mockCalendarEvents: CalendarEvent[] = [
  {
    id: "cal1",
    title: "Non-Farm Payrolls",
    country: "USD",
    impact: "high",
    forecast: "185K",
    previous: "228K",
    scheduledAt: new Date(Date.now() + 2 * 3600000),
  },
  {
    id: "cal2",
    title: "Fed Interest Rate Decision",
    country: "USD",
    impact: "high",
    forecast: "5.25%",
    previous: "5.25%",
    scheduledAt: new Date(Date.now() + 26 * 3600000),
  },
  {
    id: "cal3",
    title: "US CPI (YoY)",
    country: "USD",
    impact: "high",
    forecast: "3.1%",
    previous: "3.2%",
    actual: "3.2%",
    scheduledAt: new Date(Date.now() - 4 * 3600000),
  },
  {
    id: "cal4",
    title: "Initial Jobless Claims",
    country: "USD",
    impact: "medium",
    forecast: "220K",
    previous: "215K",
    scheduledAt: new Date(Date.now() + 8 * 3600000),
  },
  {
    id: "cal5",
    title: "ECB Press Conference",
    country: "EUR",
    impact: "high",
    forecast: "-",
    previous: "-",
    scheduledAt: new Date(Date.now() + 50 * 3600000),
  },
];

// --- Generate OHLCV Mock Data ---
export function generateMockCandles(count: number = 200, basePrice: number = 3300): CandleData[] {
  const candles: CandleData[] = [];
  let price = basePrice;
  const now = Math.floor(Date.now() / 1000);
  const interval = 3600; // 1h candles

  for (let i = count; i > 0; i--) {
    const time = now - i * interval;
    const volatility = 2 + Math.random() * 8;
    const direction = Math.random() > 0.48 ? 1 : -1;
    const open = price;
    const close = open + direction * volatility;
    const high = Math.max(open, close) + Math.random() * 4;
    const low = Math.min(open, close) - Math.random() * 4;
    const volume = Math.floor(1000 + Math.random() * 5000);

    candles.push({
      time,
      open: parseFloat(open.toFixed(2)),
      high: parseFloat(high.toFixed(2)),
      low: parseFloat(low.toFixed(2)),
      close: parseFloat(close.toFixed(2)),
      volume,
    });

    price = close;
  }

  return candles;
}

// --- Current Price Mock (realistic fallback — replaced by live data immediately) ---
export const mockCurrentPrice = {
  bid: 4627.00,
  ask: 4627.30,
  spread: 0.30,
  change: 0,
  changePercent: 0,
  high24h: 4627.00,
  low24h: 4627.00,
};

// --- Account Stats ---
export const mockAccountStats = {
  winRate: 72.5,
  totalSignals: 156,
  profitFactor: 2.3,
  avgConfidence: 76.4,
  todayPnl: 45.30,
  weekPnl: 218.50,
};
