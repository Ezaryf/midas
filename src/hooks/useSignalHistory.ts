"use client";

import { useState, useEffect } from "react";
import { createClient } from "@/utils/supabase/client";
import type { TradeSignal } from "@/lib/types";

export function useSignalHistory() {
  const [signals, setSignals] = useState<TradeSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);
  const supabase = createClient();

  useEffect(() => {
    const load = async () => {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) { setLoading(false); return; }

      const { data, error } = await supabase
        .from("signals")
        .select("*")
        .eq("user_id", user.id)
        .order("created_at", { ascending: false })
        .limit(50);

      if (!error && data) {
        setSignals(data.map(r => ({
          id:            r.id,
          signal_id:     r.id,
          symbol:        r.symbol,
          analysis_batch_id: r.analysis_batch_id,
          timestamp:     r.created_at,
          direction:     r.direction,
          entry_price:   r.entry_price,
          stop_loss:     r.stop_loss,
          take_profit_1: r.take_profit_1,
          take_profit_2: r.take_profit_2,
          confidence:    r.confidence,
          reasoning:     r.reasoning,
          trading_style: r.trading_style,
          setup_type:    r.setup_type,
          market_regime: r.market_regime,
          score:         r.score,
          rank:          r.rank,
          is_primary:    r.is_primary,
          entry_window_low: r.entry_window_low,
          entry_window_high: r.entry_window_high,
          context_tags:  r.context_tags,
          source:        r.source,
          status:        r.status,
          outcome:       r.outcome,
        })));
      }
      setLoading(false);
    };

    load();

    const channel = supabase
      .channel("signals-changes")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "signals" },
        (payload) => {
          const r = payload.new;
          setSignals(prev => [{
            id:            r.id,
            signal_id:     r.id,
            symbol:        r.symbol,
            analysis_batch_id: r.analysis_batch_id,
            timestamp:     r.created_at,
            direction:     r.direction,
            entry_price:   r.entry_price,
            stop_loss:     r.stop_loss,
            take_profit_1: r.take_profit_1,
            take_profit_2: r.take_profit_2,
            confidence:    r.confidence,
            reasoning:     r.reasoning,
            trading_style: r.trading_style,
            setup_type:    r.setup_type,
            market_regime: r.market_regime,
            score:         r.score,
            rank:          r.rank,
            is_primary:    r.is_primary,
            entry_window_low: r.entry_window_low,
            entry_window_high: r.entry_window_high,
            context_tags:  r.context_tags,
            source:        r.source,
            status:        r.status,
            outcome:       r.outcome,
          }, ...prev].slice(0, 50));
        })
      .subscribe();

    return () => { supabase.removeChannel(channel); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const clearHistory = async () => {
    setClearing(true);
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;
      await supabase.from("signals").delete().eq("user_id", user.id);
      setSignals([]);
    } finally {
      setClearing(false);
    }
  };

  return { signals, loading, clearing, clearHistory };
}
