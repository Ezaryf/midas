"use client";

import { useEffect, useRef } from "react";
import { createClient } from "@/utils/supabase/client";
import { useMidasStore } from "@/store/useMidasStore";
import type { TradeSignal } from "@/lib/types";

/**
 * Watches the Zustand store for new signals and persists them to Supabase.
 * Mount this once in the dashboard.
 */
export function useSignalPersistence() {
  const supabase = createClient();
  const savedKeysRef = useRef<Set<string>>(new Set());

  const saveSignal = async (signal: TradeSignal) => {
    // CRITICAL FIX: Validate trading_style before saving
    if (!signal.trading_style || !["Scalper", "Intraday", "Swing"].includes(signal.trading_style)) {
      console.warn("⚠️ Signal has invalid trading_style, skipping save:", signal);
      return;
    }
    
    // Deduplicate — don't save the same signal twice
    const dedupeKey =
      signal.id ||
      signal.signal_id ||
      (signal.analysis_batch_id
        ? `${signal.analysis_batch_id}-${signal.rank ?? 1}`
        : `${signal.direction}-${signal.entry_price}-${signal.timestamp}`);
    if (savedKeysRef.current.has(dedupeKey)) return;
    savedKeysRef.current.add(dedupeKey);

    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    await supabase.from("signals").insert({
      user_id:       user.id,
      direction:     signal.direction,
      symbol:        signal.symbol ?? "XAUUSD",
      analysis_batch_id: signal.analysis_batch_id,
      entry_price:   signal.entry_price,
      stop_loss:     signal.stop_loss,
      take_profit_1: signal.take_profit_1,
      take_profit_2: signal.take_profit_2,
      confidence:    signal.confidence,
      reasoning:     signal.reasoning,
      trading_style: signal.trading_style,
      setup_type:    signal.setup_type,
      market_regime: signal.market_regime,
      score:         signal.score,
      rank:          signal.rank,
      is_primary:    signal.is_primary,
      entry_window_low: signal.entry_window_low,
      entry_window_high: signal.entry_window_high,
      context_tags:  signal.context_tags ?? [],
      source:        signal.source,
      status:        signal.status ?? (signal.is_primary === false ? "PENDING" : "ACTIVE"),
    });
    
    console.log(`✅ Saved ${signal.trading_style} signal to database`);
  };

  // Subscribe to store changes
  useEffect(() => {
    return useMidasStore.subscribe((state) => {
      if (state.latestBatch) {
        saveSignal(state.latestBatch.primary);
        state.latestBatch.backups?.forEach((signal) => saveSignal(signal));
        return;
      }
      if (state.activeSignal) saveSignal(state.activeSignal);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
