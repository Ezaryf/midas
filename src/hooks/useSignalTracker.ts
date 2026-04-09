"use client";
// Cache-bust: Verified Supabase removal
import { useEffect, useRef } from "react";
import { useLivePrice } from "./useLivePrice";
import { useMidasStore } from "@/store/useMidasStore";

/**
 * Watches live price against the active signal in the Zustand store.
 * Updates signal status to HIT_TP1, HIT_TP2, or STOPPED automatically.
 * All tracking is done in-memory — no external DB calls.
 */
export function useSignalTracker() {
  const { data: livePrice } = useLivePrice();
  const processingRef = useRef(false);
  const { activeSignal, clearActiveSignal } = useMidasStore();

  useEffect(() => {
    if (!livePrice || !activeSignal || processingRef.current) return;

    processingRef.current = true;
    try {
      const price = livePrice.price;
      const sig = activeSignal;
      const isBuy = sig.direction === "BUY";

      let newStatus: string | null = null;

      if (isBuy) {
        if (price >= sig.take_profit_2) {
          newStatus = "HIT_TP2";
        } else if (price >= sig.take_profit_1) {
          newStatus = "HIT_TP1";
        } else if (price <= sig.stop_loss) {
          newStatus = "STOPPED";
        }
      } else if (sig.direction === "SELL") {
        if (price <= sig.take_profit_2) {
          newStatus = "HIT_TP2";
        } else if (price <= sig.take_profit_1) {
          newStatus = "HIT_TP1";
        } else if (price >= sig.stop_loss) {
          newStatus = "STOPPED";
        }
      }

      if (newStatus) {
        console.log(`[SignalTracker] Signal ${sig.id ?? "active"} → ${newStatus} @ ${price}`);
        clearActiveSignal();
      }
    } finally {
      processingRef.current = false;
    }
  }, [livePrice]); // eslint-disable-line react-hooks/exhaustive-deps
}
