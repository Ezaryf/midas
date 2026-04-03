"use client";

import { useConnectionStatus } from "@/hooks/useConnectionStatus";
import { useMidasStore } from "@/store/useMidasStore";
import { Server, Wifi, WifiOff, RefreshCw } from "lucide-react";
import Link from "next/link";

export default function StatusBar() {
  const { state, checkBackend } = useConnectionStatus();
  const currentPrice = useMidasStore(s => s.currentPrice);

  return (
    <div className="flex items-center gap-1 px-4 py-1.5 border-b border-border bg-surface/30 text-[10px] overflow-x-auto">

      {/* Backend pill */}
      <div className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 border ${
        state.backend === "connected" ? "border-bullish/20 bg-bullish/5 text-bullish" :
        state.backend === "checking"  ? "border-warning/20 bg-warning/5 text-warning" :
        state.backend === "error"     ? "border-bearish/20 bg-bearish/5 text-bearish" :
        "border-border text-text-muted"
      }`}>
        <span className={`h-1.5 w-1.5 rounded-full ${
          state.backend === "connected" ? "bg-bullish animate-pulse" :
          state.backend === "checking"  ? "bg-warning animate-pulse" :
          state.backend === "error"     ? "bg-bearish" : "bg-text-muted"
        }`} />
        <Server className="h-3 w-3" />
        <span className="whitespace-nowrap">
          {state.backend === "connected" ? "Backend Online" :
           state.backend === "checking"  ? "Checking..." :
           state.backend === "error"     ? "Backend Offline" : "Backend"}
        </span>
        {state.backend !== "checking" && (
          <button onClick={checkBackend} className="ml-0.5 opacity-60 hover:opacity-100">
            <RefreshCw className="h-2.5 w-2.5" />
          </button>
        )}
      </div>

      <span className="text-border mx-1">·</span>

      {/* MT5 pill */}
      <div className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 border ${
        state.mt5 === "connected" ? "border-bullish/20 bg-bullish/5 text-bullish" : "border-border text-text-muted"
      }`}>
        <span className={`h-1.5 w-1.5 rounded-full ${state.mt5 === "connected" ? "bg-bullish animate-pulse" : "bg-text-muted"}`} />
        {state.mt5 === "connected" ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
        <span className="whitespace-nowrap">
          {state.mt5 === "connected"
            ? currentPrice ? `MT5 · ${currentPrice.bid}` : "MT5 Connected"
            : "MT5 Offline"}
        </span>
      </div>

      {/* Offline hints */}
      {state.backend === "error" && (
        <>
          <span className="text-border mx-1">—</span>
          <span className="text-text-muted whitespace-nowrap">
            Run <code className="font-[family-name:var(--font-jetbrains-mono)] text-gold">uvicorn main:app --reload</code> in <code className="font-[family-name:var(--font-jetbrains-mono)] text-gold">backend/</code>
          </span>
        </>
      )}
      {state.backend === "connected" && state.mt5 !== "connected" && (
        <>
          <span className="text-border mx-1">—</span>
          <span className="text-text-muted whitespace-nowrap">
            Run <code className="font-[family-name:var(--font-jetbrains-mono)] text-gold">python mt5_bridge.py</code> in <code className="font-[family-name:var(--font-jetbrains-mono)] text-gold">backend/</code>
          </span>
        </>
      )}

      <div className="ml-auto">
        <Link href="/config" className="text-text-muted hover:text-gold transition-colors whitespace-nowrap">
          Setup guide →
        </Link>
      </div>
    </div>
  );
}
