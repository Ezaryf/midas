"use client";

import { useState, useEffect, useRef } from "react";
import type { CandlestickData, Time } from "lightweight-charts";
import { useLivePrice } from "./useLivePrice";

export type Timeframe = "M1" | "M3" | "M5" | "M15" | "H1" | "H4" | "D1";

// How often to re-fetch the full candle history (ms)
const REFETCH_INTERVAL: Record<Timeframe, number> = {
  M1:  60_000,
  M3:  60_000,
  M5:  60_000,
  M15: 120_000,
  H1:  300_000,
  H4:  600_000,
  D1:  3_600_000,
};

export function useLiveCandles(timeframe: Timeframe = "M15") {
  const { data: livePrice } = useLivePrice();
  const [candles, setCandles] = useState<CandlestickData<Time>[]>([]);
  const [loading, setLoading] = useState(true);
  const tfRef = useRef(timeframe);

  const fetchCandles = async (tf: Timeframe) => {
    try {
      const res = await fetch(`/api/candles?tf=${tf}`);
      if (!res.ok) return;
      const json = await res.json();
      const raw: { time: number; open: number; high: number; low: number; close: number; volume?: number }[] =
        json.candles ?? [];

      if (raw.length === 0) return;
      if (tfRef.current !== tf) return;

      setCandles(
        raw.map((c) => ({
          time:   c.time as Time,
          open:   c.open,
          high:   c.high,
          low:    c.low,
          close:  c.close,
          volume: c.volume ?? 0,
        }))
      );
    } catch (e) {
      console.error("useLiveCandles fetch error:", e);
    } finally {
      setLoading(false);
    }
  };

  // Re-fetch when timeframe changes
  useEffect(() => {
    tfRef.current = timeframe;
    setLoading(true);
    fetchCandles(timeframe);

    const id = setInterval(() => fetchCandles(timeframe), REFETCH_INTERVAL[timeframe]);
    return () => clearInterval(id);
  }, [timeframe]);

  // Update the last candle's close/high/low from live price (no extra fetch needed)
  useEffect(() => {
    if (!livePrice || candles.length === 0) return;
    const price = livePrice.price;
    if (price <= 1) return; 

    // Spike Guard: Ignore ticks that are too far from the current candle (e.g. > $50 jump)
    // unless the candle is empty. This prevents broker "bad ticks" from stretching the chart.
    const lastCandle = candles.at(-1);
    if (lastCandle && Math.abs(price - lastCandle.close) > 50) {
      console.warn(`[Midas] Ignoring potential price spike: ${lastCandle.close} -> ${price}`);
      return;
    }

    setCandles((prev) => {
      if (prev.length === 0) return prev;
      const last = prev.at(-1);
      if (!last) return prev;
      const updated: CandlestickData<Time> & { volume?: number } = {
        time:   last.time,
        open:   last.open,
        high:   Math.max(last.high, price),
        low:    Math.min(last.low, price),
        close:  price,
        volume: (last as CandlestickData<Time> & { volume?: number }).volume,
      };
      return [...prev.slice(0, -1), updated];
    });
  }, [livePrice]); // eslint-disable-line react-hooks/exhaustive-deps

  return { candles, loading };
}
