"use client";

import { useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useMidasStore } from "@/store/useMidasStore";
import { fetchWithSchema } from "@/lib/http";
import { backendHealthSchema } from "@/lib/schemas/api";

export type ServiceStatus = "idle" | "checking" | "connected" | "error";

export interface ConnectionState {
  backend: ServiceStatus;
  mt5: ServiceStatus;
  backendMsg: string;
  mt5Msg: string;
  latestPrice: number | null;
  mt5Account: string | null;
}

export function useConnectionStatus() {
  const isMt5Connected = useMidasStore((s) => s.isConnected);
  const currentPrice = useMidasStore((s) => s.currentPrice);

  const backendQuery = useQuery({
    queryKey: ["backend-health"],
    queryFn: () => fetchWithSchema("/api/backend/health", backendHealthSchema),
    refetchInterval: 15_000,
    retry: 0,
  });

  const checkBackend = useCallback(async () => {
    await backendQuery.refetch();
  }, [backendQuery]);

  const mt5Status = isMt5Connected ? ("connected" as const) : ("error" as const);
  const mt5Msg = isMt5Connected
    ? currentPrice
      ? `Live · ${currentPrice.symbol} ${currentPrice.bid}`
      : "Connected"
    : "Not connected — run start_bridge.bat in backend/";

  const state: ConnectionState = {
    backend: backendQuery.isLoading
      ? "checking"
      : backendQuery.isError || backendQuery.data?.status === "offline"
        ? "error"
        : "connected",
    mt5: mt5Status,
    backendMsg: backendQuery.isLoading
      ? "Connecting..."
      : backendQuery.isError || backendQuery.data?.status === "offline"
        ? "Cannot reach localhost:8000 — run start.bat in backend/"
        : "Online · port 8000",
    mt5Msg,
    latestPrice: backendQuery.data?.latest_price ?? null,
    mt5Account: null,
  };

  return { state, checkBackend };
}
