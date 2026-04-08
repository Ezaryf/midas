"use client";

import { useState, useEffect } from "react";
import { createClient } from "@/utils/supabase/client";

export interface PerformanceStats {
  totalSignals:  number;
  wins:          number;
  losses:        number;
  winRate:       number;
  grossProfit:   number;
  grossLoss:     number;
  totalPnl:      number;
  todayPnl:      number;
  weekPnl:       number;
  profitFactor:  number;
}

const EMPTY: PerformanceStats = {
  totalSignals: 0, wins: 0, losses: 0, winRate: 0,
  grossProfit: 0, grossLoss: 0, totalPnl: 0, todayPnl: 0, weekPnl: 0, profitFactor: 0,
};

const getUserWithRetry = async (supabase: ReturnType<typeof createClient>, retries = 3) => {
  for (let i = 0; i < retries; i++) {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      return user;
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      if (errorMsg.includes("lock") && i < retries - 1) {
        await new Promise(r => setTimeout(r, (i + 1) * 500));
        continue;
      }
      throw err;
    }
  }
  return null;
};

export function usePerformance() {
  const [stats, setStats]     = useState<PerformanceStats>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [resetting, setResetting] = useState(false);
  const supabase = createClient();

  const load = async () => {
    const user = await getUserWithRetry(supabase);
    if (!user) { setLoading(false); return; }

    const { data } = await supabase
      .from("signal_performance")
      .select("*")
      .eq("user_id", user.id)
      .maybeSingle();

    if (data) {
      const gp = parseFloat(data.gross_profit ?? 0);
      const gl = parseFloat(data.gross_loss   ?? 0);
      setStats({
        totalSignals: parseInt(data.total_signals ?? 0),
        wins:         parseInt(data.wins          ?? 0),
        losses:       parseInt(data.losses        ?? 0),
        winRate:      parseFloat(data.win_rate     ?? 0),
        grossProfit:  gp,
        grossLoss:    gl,
        totalPnl:     parseFloat(data.total_pnl   ?? 0),
        todayPnl:     parseFloat(data.today_pnl   ?? 0),
        weekPnl:      parseFloat(data.week_pnl    ?? 0),
        profitFactor: gl > 0 ? parseFloat((gp / gl).toFixed(2)) : gp > 0 ? 999 : 0,
      });
    } else {
      setStats(EMPTY);
    }
    setLoading(false);
  };

  const resetPerformance = async () => {
    setResetting(true);
    try {
      const user = await getUserWithRetry(supabase);
      if (!user) return;
      await supabase.from("signals").delete().eq("user_id", user.id);
      setStats(EMPTY);
    } finally {
      setResetting(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return { stats, loading, resetting, resetPerformance };
}
