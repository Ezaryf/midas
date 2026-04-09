"use client";

import { useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { CandlestickData, Time } from "lightweight-charts";
import { useLivePrice } from "./useLivePrice";
import { useMidasStore } from "@/store/useMidasStore";
import { fetchWithSchema } from "@/lib/http";
import { candlesResponseSchema } from "@/lib/schemas/api";

export type Timeframe = "M1" | "M3" | "M5" | "M15" | "H1" | "H2" | "H4" | "D1";

const REFETCH_INTERVAL: Record<Timeframe, number> = {
  M1: 60_000,
  M3: 60_000,
  M5: 60_000,
  M15: 120_000,
  H1: 300_000,
  H2: 300_000,
  H4: 600_000,
  D1: 3_600_000,
};

interface CandleWithVolume extends CandlestickData<Time> {
  volume?: number;
}

export function useLiveCandles(timeframe: Timeframe = "M15") {
  const { data: livePrice } = useLivePrice();
  const targetSymbol = useMidasStore((s) => s.targetSymbol);
  const setCalibrationFactor = useMidasStore((s) => s.setCalibrationFactor);

  const candlesQuery = useQuery({
    queryKey: ["candles", timeframe, targetSymbol],
    queryFn: async () => {
      const data = await fetchWithSchema(`/api/candles?tf=${timeframe}&symbol=${targetSymbol}`, candlesResponseSchema);
      return data.candles
        .filter((c) => c.open > 1 && c.close > 1)
        .map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          volume: c.volume ?? 0,
        })) satisfies CandleWithVolume[];
    },
    refetchInterval: REFETCH_INTERVAL[timeframe],
  });

  const baseCandles = useMemo(
    () => candlesQuery.data ?? [],
    [candlesQuery.data]
  );

  useEffect(() => {
    if (livePrice?.price && baseCandles.length > 0) {
      const histClose = baseCandles.at(-1)!.close;
      const liveRaw = livePrice.price;

      if (Math.abs(liveRaw - histClose) / histClose > 0.20) {
        const factor = histClose / liveRaw;
        console.log(`[Midas] Calibrating price scale: ${liveRaw} -> ${histClose} (factor: ${factor.toFixed(4)})`);
        setCalibrationFactor(factor);
      }
    }
  }, [baseCandles, livePrice?.price, setCalibrationFactor]);

  const candles = useMemo(() => {
    if (!livePrice || baseCandles.length === 0) return baseCandles;

    const price = livePrice.price;
    if (!price || price <= 1) return baseCandles;

    const lastCandle = baseCandles.at(-1);
    if (!lastCandle) return baseCandles;

    const threshold = lastCandle.close * 0.03;
    const diff = Math.abs(price - lastCandle.close);
    if (diff > threshold) {
      console.warn(`[Midas] Spike Guard (Web): Ignoring price ${price.toFixed(2)} (diff ${diff.toFixed(2)} > ${threshold.toFixed(2)} from ${lastCandle.close.toFixed(2)})`);
      return baseCandles;
    }

    const updated: CandleWithVolume = {
      time: lastCandle.time,
      open: lastCandle.open,
      high: Math.max(lastCandle.high, price),
      low: Math.min(lastCandle.low, price),
      close: price,
      volume: lastCandle.volume,
    };

    return [...baseCandles.slice(0, -1), updated];
  }, [baseCandles, livePrice]);

  return { candles, loading: candlesQuery.isLoading };
}
