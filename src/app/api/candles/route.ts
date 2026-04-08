import { NextRequest, NextResponse } from "next/server";

const INTERVAL_MAP: Record<string, string> = {
  M1:  "1m",
  M3:  "1m",  // Yahoo doesn't have 3m, we'll aggregate from 1m
  M5:  "5m",
  M15: "15m",
  H1:  "60m",
  H2:  "60m", // Aggregate 2x 60m
  H4:  "60m", // Aggregate 4x 60m
  D1:  "1d",
};

const RANGE_MAP: Record<string, string> = {
  M1:  "5d",  // Max 7d for 1m
  M3:  "5d", 
  M5:  "1mo", // Max 60d for 5m
  M15: "1mo",
  H1:  "3mo",
  H2:  "3mo",
  H4:  "6mo",
  D1:  "2y",
};

const SYMBOL_MAP: Record<string, string> = {
  "XAUUSD": "GC=F",
  "XAGUSD": "SI=F",
  "BTCUSD": "BTC-USD",
  "EURUSD": "EURUSD=X",
  "GBPUSD": "GBPUSD=X",
  "USDJPY": "JPY=X",
};

export async function GET(req: NextRequest) {
  const tf = req.nextUrl.searchParams.get("tf") ?? "M15";
  const symbol = req.nextUrl.searchParams.get("symbol") ?? "XAUUSD";
  
  const interval = INTERVAL_MAP[tf] ?? "15m";
  const range = RANGE_MAP[tf] ?? "5d";
  const yfTicker = SYMBOL_MAP[symbol] ?? "GC=F";

  const url = `https://query2.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yfTicker)}?interval=${interval}&range=${range}`;

  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0" },
      next: { revalidate: 10 }, // cache for 10s
    });

    if (!res.ok) {
      return NextResponse.json({ error: "Upstream error" }, { status: 502 });
    }

    const json = await res.json();
    const result = json?.chart?.result?.[0];

    if (!result) {
      return NextResponse.json({ error: "No data" }, { status: 502 });
    }

    const timestamps: number[] = result.timestamp ?? [];
    const quote = result.indicators?.quote?.[0] ?? {};
    const opens: number[]   = quote.open   ?? [];
    const highs: number[]   = quote.high   ?? [];
    const lows: number[]    = quote.low    ?? [];
    const closes: number[]  = quote.close  ?? [];
    const volumes: number[] = quote.volume ?? [];

    // Build candles, skip any with null values (market closed gaps)
    const rawCandles = timestamps
      .map((t, i) => ({
        time:   t,
        open:   opens[i],
        high:   highs[i],
        low:    lows[i],
        close:  closes[i],
        volume: volumes[i] ?? 0,
      }))
      .filter((c) => c.open > 1 && c.high > 1 && c.low > 1 && c.close > 1);

    // Sanitize Yahoo Finance historical data
    // Remove "glitch" candles with massive phantom wicks (common in real-time YF futures data)
    const candles = [];
    const sizes = [];
    
    // Sort slightly needed to determine median but only store recent 10 sizes
    for (let i = 0; i < rawCandles.length; i++) {
        const c = rawCandles[i];
        const size = c.high - c.low;
        
        if (sizes.length >= 5) {
            const recentSizes = [...sizes].slice(-10).sort((a,b) => a - b);
            const mid = Math.floor(recentSizes.length / 2);
            const medianSize = recentSizes.length % 2 !== 0 ? recentSizes[mid] : (recentSizes[mid - 1] + recentSizes[mid]) / 2;
            
            // If the candle has a body/wick that is >12x the median recent size, it's almost certainly a YF glitch
            if (medianSize > 0 && size > medianSize * 15) {
                console.warn(`[Midas] ⚠️ Filtering anomaly YF candle at ${c.time}: High ${c.high}, Low ${c.low} (size ${size} vs median ${medianSize})`);
                continue; // Skip this anomaly
            }

            // Also check for massive gap from the previous close (e.g. >2% jump in one candle is a glitch for Gold)
            const prevClose = candles[candles.length - 1]?.close;
            if (prevClose) {
                const gap = Math.abs(c.open - prevClose) / prevClose;
                if (gap > 0.02 && tf !== "D1") { // 2% gap intra-day is practically impossible in metals/forex
                    console.warn(`[Midas] ⚠️ Filtering gap anomaly YF candle at ${c.time}: gap ${gap.toFixed(3)}%`);
                    continue;
                }
            }
        }
        
        candles.push(c);
        sizes.push(size);
    }

    // For H4: aggregate 60m candles into 4h buckets
    if (tf === "H4") {
      const aggregated: typeof candles = [];
      for (let i = 0; i < candles.length; i += 4) {
        const chunk = candles.slice(i, i + 4);
        if (chunk.length === 0) continue;
        aggregated.push({
          time:   chunk[0].time,
          open:   chunk[0].open,
          high:   Math.max(...chunk.map((c) => c.high)),
          low:    Math.min(...chunk.map((c) => c.low)),
          close:  chunk.at(-1)!.close,
          volume: chunk.reduce((s, c) => s + (c.volume ?? 0), 0),
        });
      }
      return NextResponse.json({ candles: aggregated });
    }

    // For H2: aggregate 60m candles into 2h buckets
    if (tf === "H2") {
      const aggregated: typeof candles = [];
      for (let i = 0; i < candles.length; i += 2) {
        const chunk = candles.slice(i, i + 2);
        if (chunk.length === 0) continue;
        aggregated.push({
          time:   chunk[0].time,
          open:   chunk[0].open,
          high:   Math.max(...chunk.map((c) => c.high)),
          low:    Math.min(...chunk.map((c) => c.low)),
          close:  chunk.at(-1)!.close,
          volume: chunk.reduce((s, c) => s + (c.volume ?? 0), 0),
        });
      }
      return NextResponse.json({ candles: aggregated });
    }

    // For M3: aggregate 1m candles into 3m buckets
    if (tf === "M3") {
      const aggregated: typeof candles = [];
      for (let i = 0; i < candles.length; i += 3) {
        const chunk = candles.slice(i, i + 3);
        if (chunk.length === 0) continue;
        aggregated.push({
          time:   chunk[0].time,
          open:   chunk[0].open,
          high:   Math.max(...chunk.map((c) => c.high)),
          low:    Math.min(...chunk.map((c) => c.low)),
          close:  chunk.at(-1)!.close,
          volume: chunk.reduce((s, c) => s + (c.volume ?? 0), 0),
        });
      }
      return NextResponse.json({ candles: aggregated });
    }

    return NextResponse.json({ candles });
  } catch (e) {
    console.error("Candles API error:", e);
    return NextResponse.json({ error: "Failed to fetch candles" }, { status: 500 });
  }
}
