"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchWithSchema } from "@/lib/http";
import { positionsResponseSchema } from "@/lib/schemas/api";

export interface Position {
  ticket: number;
  symbol: string;
  type: string;
  volume: number;
  open_price: number;
  current_price: number;
  sl: number;
  tp: number;
  profit: number;
  swap: number;
  commission: number;
  open_time: string;
  comment: string;
}

export function usePositions(refreshInterval: number = 5000) {
  const query = useQuery({
    queryKey: ["positions"],
    queryFn: async () => {
      const data = await fetchWithSchema("/api/positions", positionsResponseSchema);
      return data.positions as Position[];
    },
    refetchInterval: refreshInterval,
  });

  return {
    positions: query.data ?? [],
    loading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
