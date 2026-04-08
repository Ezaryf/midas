"use client";

import { useState, useEffect, useRef } from "react";
import type { CandlestickData, Time } from "lightweight-charts";
import { useLivePrice } from "./useLivePrice";
import { useMidasStore } from "@/store/useMidasStore";

export type Timeframe = "M1" | "M3" | "M5" | "M15" | "H1" | "H2" | "H4" | "D1";

// How often to re-fetch the full candle history (ms)
const REFETCH_INTERVAL: Record<Timeframe, number> = {
  M1:  60_000,
  M3:  60_000,
  M5:  60_000,
  M15: 120_000,
  H1:  300_000,
  H2:  300_000,
  H4:  600_000,
  D1:  3_600_000,
};

export function useLiveCandles(timeframe: Timeframe = "M15") {
  const { data: livePrice } = useLivePrice();
  const targetSymbol = useMidasStore(s => s.targetSymbol);
  
  const [candles, setCandles] = useState<CandlestickData<Time>[]>([]);
  const [loading, setLoading] = useState(true);
  const tfRef = useRef(timeframe);
  const symRef = useRef(targetSymbol);

  const setCalibrationFactor = useMidasStore(s => s.setCalibrationFactor);
  
  const fetchCandles = async (tf: Timeframe, sym: string) => {
    try {
      const res = await fetch(`/api/candles?tf=${tf}&symbol=${sym}`);
      if (!res.ok) return;
      const json = await res.json();
      const raw: { time: number; open: number; high: number; low: number; close: number; volume?: number }[] =
        json.candles ?? [];

      if (raw.length === 0) {
        setCandles([]);
        return;
      }
      if (tfRef.current !== tf || symRef.current !== sym) return;

      const formatted = raw
        .filter((c) => c.open > 1 && c.close > 1) // Secondary filter
        .map((c) => ({
          time:   c.time as Time,
          open:   c.open,
          high:   c.high,
          low:    c.low,
          close:  c.close,
          volume: c.volume ?? 0,
        }));

      setCandles(formatted);
    } catch (e) {
      console.error("useLiveCandles fetch error:", e);
    } finally {
      setLoading(false);
    }
  };

  // --- AUTO-CALIBRATION EFFECT ---
  // If we have live data and history, check for scaling mismatch (e.g. 2600 vs 4800)
  // Only runs when history is first successfully fetched
  useEffect(() => {
    if (livePrice?.price && candles.length > 0) {
      const histClose = candles.at(-1)!.close;
      const liveRaw = livePrice.price;
      
      // If difference is > 20%, calculate calibration factor
      if (Math.abs(liveRaw - histClose) / histClose > 0.20) {
        const factor = histClose / liveRaw;
        console.log(`[Midas] ⚖️ Calibrating price scale: ${liveRaw} -> ${histClose} (factor: ${factor.toFixed(4)})`);
        setCalibrationFactor(factor);
      }
    }
  }, [candles.length > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch when timeframe or symbol changes
  useEffect(() => {
    tfRef.current = timeframe;
    symRef.current = targetSymbol;
    setLoading(true);
    fetchCandles(timeframe, targetSymbol);

    const id = setInterval(() => fetchCandles(timeframe, targetSymbol), REFETCH_INTERVAL[timeframe]);
    return () => clearInterval(id);
  }, [timeframe, targetSymbol]); // eslint-disable-line react-hooks/exhaustive-deps

  // Update the last candle's close/high/low from live price
  useEffect(() => {
    if (!livePrice || candles.length === 0) return;
    
    // The useLivePrice hook already filters by targetSymbol, but we'll be extra safe
    const price = livePrice.price;
    if (!price || price <= 1) return; 

    // Spike Guard: Ignore ticks that are too far from the current candle
    const lastCandle = candles.at(-1);
    if (!lastCandle) return;

    // Use a more permissible threshold (3.0% (~140 pts) vs previous 0.5%)
    // This allows the initial "snap" and legitimate high-impact news moves.
    const THRESHOLD = lastCandle.close * 0.03; 
    const diff = Math.abs(price - lastCandle.close);
    
    if (diff > THRESHOLD) {
      console.warn(`[Midas] 🛡️ Spike Guard (Web): Ignoring price ${price.toFixed(2)} (diff ${diff.toFixed(2)} > ${THRESHOLD.toFixed(2)} from ${lastCandle.close.toFixed(2)})`);
      return;
    }

    setCandles((prev) => {
      const last = prev.at(-1);
      if (!last) return prev;
      
      const updated: CandlestickData<Time> = {
        time:   last.time,
        open:   last.open,
        high:   Math.max(last.high, price),
        low:    Math.min(last.low, price),
        close:  price,
      };
      return [...prev.slice(0, -1), updated];
    });
  }, [livePrice]); // eslint-disable-line react-hooks/exhaustive-deps

  return { candles, loading };
}
