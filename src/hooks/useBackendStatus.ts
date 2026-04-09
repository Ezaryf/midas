"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchWithSchema } from "@/lib/http";
import { backendHealthSchema } from "@/lib/schemas/api";

export type BackendStatus = "checking" | "online" | "offline";

export function useBackendStatus() {
  const query = useQuery({
    queryKey: ["backend-health"],
    queryFn: () => fetchWithSchema("/api/backend/health", backendHealthSchema),
    refetchInterval: 15_000,
    retry: 0,
  });

  if (query.isLoading) return "checking";
  return query.isError ? "offline" : "online";
}
