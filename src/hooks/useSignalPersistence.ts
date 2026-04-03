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
  const lastSavedId = useRef<string | null>(null);

  const saveSignal = async (signal: TradeSignal) => {
    // CRITICAL FIX: Validate trading_style before saving
    if (!signal.trading_style || !["Scalper", "Intraday", "Swing"].includes(signal.trading_style)) {
      console.warn("⚠️ Signal has invalid trading_style, skipping save:", signal);
      return;
    }
    
    // Deduplicate — don't save the same signal twice
    const dedupeKey = `${signal.direction}-${signal.entry_price}-${signal.timestamp}`;
    if (lastSavedId.current === dedupeKey) return;
    lastSavedId.current = dedupeKey;

    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;

    await supabase.from("signals").insert({
      user_id:       user.id,
      direction:     signal.direction,
      entry_price:   signal.entry_price,
      stop_loss:     signal.stop_loss,
      take_profit_1: signal.take_profit_1,
      take_profit_2: signal.take_profit_2,
      confidence:    signal.confidence,
      reasoning:     signal.reasoning,
      trading_style: signal.trading_style,
      status:        signal.status ?? "ACTIVE",
    });
    
    console.log(`✅ Saved ${signal.trading_style} signal to database`);
  };

  // Subscribe to store changes
  useEffect(() => {
    return useMidasStore.subscribe((state) => {
      if (state.activeSignal) saveSignal(state.activeSignal);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
