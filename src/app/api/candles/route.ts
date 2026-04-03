import { NextRequest, NextResponse } from "next/server";

const INTERVAL_MAP: Record<string, string> = {
  M1:  "1m",
  M3:  "1m",  // Yahoo doesn't have 3m, we'll aggregate from 1m
  M5:  "5m",
  M15: "15m",
  H1:  "60m",
  H4:  "1h",   // Yahoo doesn't have 4h — we'll aggregate client-side
  D1:  "1d",
};

const RANGE_MAP: Record<string, string> = {
  M1:  "1d",
  M3:  "1d",
  M5:  "5d",
  M15: "5d",
  H1:  "1mo",
  H4:  "3mo",
  D1:  "1y",
};

export async function GET(req: NextRequest) {
  const tf = req.nextUrl.searchParams.get("tf") ?? "M15";
  const interval = INTERVAL_MAP[tf] ?? "15m";
  const range = RANGE_MAP[tf] ?? "5d";

  const url = `https://query2.finance.yahoo.com/v8/finance/chart/GC%3DF?interval=${interval}&range=${range}`;

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
    const candles = timestamps
      .map((t, i) => ({
        time:   t,
        open:   opens[i],
        high:   highs[i],
        low:    lows[i],
        close:  closes[i],
        volume: volumes[i] ?? 0,
      }))
      .filter((c) => c.open != null && c.close != null);

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
          close:  chunk[chunk.length - 1].close,
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
          close:  chunk[chunk.length - 1].close,
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
