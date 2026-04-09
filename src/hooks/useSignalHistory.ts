"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { TradeSignal } from "@/lib/types";
import { fetchWithSchema } from "@/lib/http";
import { signalHistoryResponseSchema } from "@/lib/schemas/api";

export function useSignalHistory() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["signal-history"],
    queryFn: async () => {
      const data = await fetchWithSchema("/api/signals/history", signalHistoryResponseSchema);
      return data.signals as TradeSignal[];
    },
    retry: 0,
    // Poll every 30s to pick up new signals saved by the Python backend
    refetchInterval: 30_000,
  });

  const clearMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch("/api/signals/history", { method: "DELETE" });
      if (!response.ok) {
        throw new Error("Failed to clear history");
      }
    },
    onSuccess: () => {
      queryClient.setQueryData(["signal-history"], []);
    },
  });

  return {
    signals: query.data ?? [],
    loading: query.isLoading,
    clearing: clearMutation.isPending,
    clearHistory: () => clearMutation.mutateAsync(),
  };
}
