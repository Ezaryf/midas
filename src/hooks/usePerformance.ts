"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchWithSchema } from "@/lib/http";
import { performanceResponseSchema } from "@/lib/schemas/api";

export interface PerformanceStats {
  totalSignals: number;
  wins: number;
  losses: number;
  winRate: number;
  grossProfit: number;
  grossLoss: number;
  totalPnl: number;
  todayPnl: number;
  weekPnl: number;
  profitFactor: number;
}

const EMPTY: PerformanceStats = {
  totalSignals: 0,
  wins: 0,
  losses: 0,
  winRate: 0,
  grossProfit: 0,
  grossLoss: 0,
  totalPnl: 0,
  todayPnl: 0,
  weekPnl: 0,
  profitFactor: 0,
};

export function usePerformance() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["signal-performance"],
    queryFn: async () => {
      const data = await fetchWithSchema("/api/signals/performance", performanceResponseSchema);
      return data.stats as PerformanceStats;
    },
    retry: 0,
    refetchInterval: 30_000,
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch("/api/signals/history", { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Failed to clear history");
      }
    },
    onSuccess: async () => {
      queryClient.setQueryData(["signal-performance"], EMPTY);
      queryClient.setQueryData(["signal-history"], []);
      await queryClient.invalidateQueries({ queryKey: ["signal-performance"] });
      await queryClient.invalidateQueries({ queryKey: ["signal-history"] });
    },
  });

  return {
    stats: query.data ?? EMPTY,
    loading: query.isLoading,
    resetting: resetMutation.isPending,
    resetPerformance: () => resetMutation.mutateAsync(),
  };
}
