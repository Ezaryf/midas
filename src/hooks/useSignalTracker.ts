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
  const resolvedRef = useRef<Set<string>>(new Set());
  const { activeSignal, clearActiveSignal } = useMidasStore();

  useEffect(() => {
    if (!livePrice || !activeSignal || processingRef.current) return;

    processingRef.current = true;
    try {
      const price = livePrice.price;
      const sig = activeSignal;
      const signalKey =
        sig.id ||
        sig.signal_id ||
        (sig.analysis_batch_id
          ? `${sig.analysis_batch_id}-${sig.rank ?? 1}`
          : `${sig.symbol || "XAUUSD"}-${sig.direction}-${sig.entry_price}`);
      if (sig.status === "HIT_TP1" || sig.status === "HIT_TP2" || sig.status === "STOPPED" || sig.status === "EXPIRED") {
        resolvedRef.current.add(signalKey);
        clearActiveSignal();
        return;
      }
      if (resolvedRef.current.has(signalKey)) {
        clearActiveSignal();
        return;
      }
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
        resolvedRef.current.add(signalKey);
        console.log(`[SignalTracker] Signal ${sig.id ?? "active"} → ${newStatus} @ ${price}`);
        useMidasStore.getState().updateSignalStatus(signalKey, newStatus as typeof sig.status);
        clearActiveSignal();
      }
    } finally {
      processingRef.current = false;
    }
  }, [livePrice]); // eslint-disable-line react-hooks/exhaustive-deps
}
