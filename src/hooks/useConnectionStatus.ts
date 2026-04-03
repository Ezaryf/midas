"use client";

import { useState, useEffect, useCallback } from "react";
import { useMidasStore } from "@/store/useMidasStore";

export type ServiceStatus = "idle" | "checking" | "connected" | "error";

export interface ConnectionState {
  backend:    ServiceStatus;
  mt5:        ServiceStatus;
  backendMsg: string;
  mt5Msg:     string;
  latestPrice: number | null;
  mt5Account:  string | null;
}

export function useConnectionStatus() {
  const isMt5Connected = useMidasStore(s => s.isConnected);
  const currentPrice   = useMidasStore(s => s.currentPrice);

  const [state, setState] = useState<ConnectionState>({
    backend: "idle", mt5: "idle",
    backendMsg: "", mt5Msg: "",
    latestPrice: null, mt5Account: null,
  });

  const checkBackend = useCallback(async () => {
    setState(s => ({ ...s, backend: "checking", backendMsg: "Connecting..." }));
    try {
      const res  = await fetch("/api/backend/health", { signal: AbortSignal.timeout(5000) });
      const data = await res.json();
      setState(s => ({
        ...s,
        backend:     data.status === "offline" ? "error" : "connected",
        backendMsg:  data.status === "offline" ? "Cannot reach backend" : "Online · port 8000",
        latestPrice: data.latest_price ?? null,
      }));
    } catch {
      setState(s => ({
        ...s,
        backend:    "error",
        backendMsg: "Cannot reach localhost:8000 — run start.bat in backend/",
      }));
    }
  }, []);

  // Sync MT5 status from WebSocket store — derive directly, no effect needed
  const mt5Status = isMt5Connected ? "connected" as const : "error" as const;
  const mt5Msg = isMt5Connected
    ? currentPrice ? `Live · ${currentPrice.symbol} ${currentPrice.bid}` : "Connected"
    : "Not connected — run start_bridge.bat in backend/";

  const fullState = { ...state, mt5: mt5Status, mt5Msg };

  // Auto-check backend on mount
  useEffect(() => {
    checkBackend();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { state: fullState, checkBackend };
}
