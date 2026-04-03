"use client";

import { useEffect, useRef } from "react";
import { createClient } from "@/utils/supabase/client";
import { useLivePrice } from "./useLivePrice";
import { useMidasStore } from "@/store/useMidasStore";

/**
 * Watches live price against active signals in Supabase.
 * Updates signal status to HIT_TP1, HIT_TP2, or STOPPED automatically.
 */
export function useSignalTracker() {
  const { data: livePrice } = useLivePrice();
  const supabase = createClient();
  const processingRef = useRef(false);
  const { activeSignal, clearActiveSignal } = useMidasStore();

  useEffect(() => {
    if (!livePrice || processingRef.current) return;

    const checkSignals = async () => {
      processingRef.current = true;
      try {
        const { data: { user } } = await supabase.auth.getUser();
        if (!user) return;

        const price = livePrice.price;

        // Fetch all active signals for this user
        const { data: active } = await supabase
          .from("signals")
          .select("id, direction, entry_price, stop_loss, take_profit_1, take_profit_2, status")
          .eq("user_id", user.id)
          .in("status", ["ACTIVE", "PENDING"]);

        if (!active || active.length === 0) return;

        for (const sig of active) {
          const isBuy = sig.direction === "BUY";
          let newStatus: string | null = null;
          let outcome: number | null = null;

          if (isBuy) {
            if (price >= sig.take_profit_2) {
              newStatus = "HIT_TP2";
              outcome   = parseFloat((sig.take_profit_2 - sig.entry_price).toFixed(2));
            } else if (price >= sig.take_profit_1) {
              newStatus = "HIT_TP1";
              outcome   = parseFloat((sig.take_profit_1 - sig.entry_price).toFixed(2));
            } else if (price <= sig.stop_loss) {
              newStatus = "STOPPED";
              outcome   = parseFloat((sig.stop_loss - sig.entry_price).toFixed(2));
            }
          } else {
            if (price <= sig.take_profit_2) {
              newStatus = "HIT_TP2";
              outcome   = parseFloat((sig.entry_price - sig.take_profit_2).toFixed(2));
            } else if (price <= sig.take_profit_1) {
              newStatus = "HIT_TP1";
              outcome   = parseFloat((sig.entry_price - sig.take_profit_1).toFixed(2));
            } else if (price >= sig.stop_loss) {
              newStatus = "STOPPED";
              outcome   = parseFloat((sig.entry_price - sig.stop_loss).toFixed(2));
            }
          }

          if (newStatus) {
            await supabase
              .from("signals")
              .update({ status: newStatus, outcome })
              .eq("id", sig.id);
            
            // If this was the active signal, clear it from the store
            if (activeSignal && activeSignal.id === sig.id) {
              clearActiveSignal();
            }
          }
        }
      } finally {
        processingRef.current = false;
      }
    };

    checkSignals();
  }, [livePrice]); // eslint-disable-line react-hooks/exhaustive-deps
}
