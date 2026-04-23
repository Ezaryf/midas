"use client";

import { useState } from "react";
import {
  Server, Wifi, WifiOff, RefreshCw, CheckCircle2, XCircle,
  Loader2, Terminal, ChevronDown, ChevronUp, Copy, Check,
} from "lucide-react";
import { useConnectionStatus, type ServiceStatus } from "@/hooks/useConnectionStatus";
import { useMidasStore } from "@/store/useMidasStore";

function StatusDot({ status }: { status: ServiceStatus }) {
  if (status === "connected") return <span className="h-2 w-2 rounded-full bg-bullish animate-pulse" />;
  if (status === "checking")  return <span className="h-2 w-2 rounded-full bg-warning animate-pulse" />;
  if (status === "error")     return <span className="h-2 w-2 rounded-full bg-bearish" />;
  return <span className="h-2 w-2 rounded-full bg-text-muted" />;
}

function StatusIcon({ status }: { status: ServiceStatus }) {
  if (status === "checking") return <Loader2 className="h-4 w-4 animate-spin text-warning" />;
  if (status === "connected") return <CheckCircle2 className="h-4 w-4 text-bullish" />;
  if (status === "error")     return <XCircle className="h-4 w-4 text-bearish" />;
  return <div className="h-4 w-4" />;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className="ml-1 text-text-muted hover:text-text-secondary transition-colors"
    >
      {copied ? <Check className="h-3 w-3 text-bullish" /> : <Copy className="h-3 w-3" />}
    </button>
  );
}

function CodeBlock({ children }: { children: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-background border border-border px-3 py-2 font-[family-name:var(--font-jetbrains-mono)] text-xs text-gold-light">
      <Terminal className="h-3 w-3 text-text-muted shrink-0" />
      <span className="flex-1">{children}</span>
      <CopyButton text={children} />
    </div>
  );
}

export default function ConnectionPanel() {
  const { state, checkBackend } = useConnectionStatus();
  const currentPrice = useMidasStore(s => s.currentPrice);
  const [showBackendSteps, setShowBackendSteps] = useState(state.backend !== "connected");
  const [showMt5Steps,     setShowMt5Steps]     = useState(false);

  return (
    <div className="space-y-4">

      {/* ── Backend Server ─────────────────────────────────────────────── */}
      <div className={`rounded-2xl border p-5 transition-colors ${
        state.backend === "connected" ? "border-bullish/20 bg-bullish/5" :
        state.backend === "error"     ? "border-bearish/20 bg-bearish/5" :
        "border-border bg-surface/50"
      }`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`flex h-9 w-9 items-center justify-center rounded-xl border ${
              state.backend === "connected" ? "bg-bullish/10 border-bullish/20" :
              state.backend === "error"     ? "bg-bearish/10 border-bearish/20" :
              "bg-surface border-border"
            }`}>
              <Server className={`h-4 w-4 ${
                state.backend === "connected" ? "text-bullish" :
                state.backend === "error"     ? "text-bearish" : "text-text-muted"
              }`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <StatusDot status={state.backend} />
                <span className="text-sm font-semibold">Python Backend</span>
              </div>
              <p className="text-xs text-text-muted mt-0.5">{state.backendMsg || "FastAPI · port 8000"}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusIcon status={state.backend} />
            <button
              onClick={checkBackend}
              disabled={state.backend === "checking"}
              className="flex items-center gap-1.5 rounded-lg bg-surface border border-border px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`h-3 w-3 ${state.backend === "checking" ? "animate-spin" : ""}`} />
              {state.backend === "checking" ? "Checking..." : "Test"}
            </button>
            <button onClick={() => setShowBackendSteps(v => !v)} className="text-text-muted hover:text-text-secondary">
              {showBackendSteps ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {showBackendSteps && (
          <div className="mt-4 space-y-3 border-t border-border pt-4">
            <p className="text-xs text-text-secondary font-medium">How to start the backend:</p>
            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold text-gold bg-gold/10 rounded px-1.5 py-0.5 mt-0.5">1</span>
                <div className="flex-1 space-y-1">
                  <p className="text-xs text-text-secondary">Open a terminal in the <code className="text-gold">backend/</code> folder</p>
                  <CodeBlock>cd backend</CodeBlock>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold text-gold bg-gold/10 rounded px-1.5 py-0.5 mt-0.5">2</span>
                <div className="flex-1 space-y-1">
                  <p className="text-xs text-text-secondary">Install dependencies (first time only)</p>
                  <CodeBlock>pip install -r requirements.txt</CodeBlock>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold text-gold bg-gold/10 rounded px-1.5 py-0.5 mt-0.5">3</span>
                <div className="flex-1 space-y-1">
                  <p className="text-xs text-text-secondary">Start the server</p>
                  <CodeBlock>uvicorn main:app --reload</CodeBlock>
                  <p className="text-[10px] text-text-muted">Or double-click <code className="text-gold">start.bat</code></p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── MT5 Bridge ─────────────────────────────────────────────────── */}
      <div className={`rounded-2xl border p-5 transition-colors ${
        state.mt5 === "connected" ? "border-bullish/20 bg-bullish/5" :
        state.mt5 === "error"     ? "border-border bg-surface/50" :
        "border-border bg-surface/50"
      }`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`flex h-9 w-9 items-center justify-center rounded-xl border ${
              state.mt5 === "connected" ? "bg-bullish/10 border-bullish/20" : "bg-surface border-border"
            }`}>
              {state.mt5 === "connected"
                ? <Wifi className="h-4 w-4 text-bullish" />
                : <WifiOff className="h-4 w-4 text-text-muted" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <StatusDot status={state.mt5} />
                <span className="text-sm font-semibold">MT5 Bridge</span>
              </div>
              <p className="text-xs text-text-muted mt-0.5">
                {state.mt5 === "connected" && currentPrice
                  ? `${currentPrice.symbol} · Bid ${currentPrice.bid} · Ask ${currentPrice.ask}`
                  : "Local Python bridge · streams live ticks"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusIcon status={state.mt5} />
            <button onClick={() => setShowMt5Steps(v => !v)} className="text-text-muted hover:text-text-secondary">
              {showMt5Steps ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* Live tick preview when connected */}
        {state.mt5 === "connected" && currentPrice && (
          <div className="mt-3 grid grid-cols-3 gap-3 rounded-xl bg-surface/60 p-3">
            <div>
              <span className="text-[10px] text-text-muted">Bid</span>
              <p className="text-sm font-bold font-[family-name:var(--font-jetbrains-mono)] text-bullish">{currentPrice.bid}</p>
            </div>
            <div>
              <span className="text-[10px] text-text-muted">Ask</span>
              <p className="text-sm font-bold font-[family-name:var(--font-jetbrains-mono)] text-bearish">{currentPrice.ask}</p>
            </div>
            <div>
              <span className="text-[10px] text-text-muted">Spread</span>
              <p className="text-sm font-bold font-[family-name:var(--font-jetbrains-mono)]">
                {currentPrice.spread != null ? currentPrice.spread.toFixed(2) : ((currentPrice.ask - currentPrice.bid).toFixed(2))}
              </p>
            </div>
          </div>
        )}

        {showMt5Steps && (
          <div className="mt-4 space-y-3 border-t border-border pt-4">
            <p className="text-xs text-text-secondary font-medium">How to connect MT5:</p>
            <div className="space-y-2">
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold text-gold bg-gold/10 rounded px-1.5 py-0.5 mt-0.5">1</span>
                <div className="flex-1 space-y-1">
                  <p className="text-xs text-text-secondary">Copy your credentials to <code className="text-gold">backend/.env</code></p>
                  <CodeBlock>cp backend/.env.example backend/.env</CodeBlock>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold text-gold bg-gold/10 rounded px-1.5 py-0.5 mt-0.5">2</span>
                <div className="flex-1 space-y-1">
                  <p className="text-xs text-text-secondary">Install MT5 Python library (Windows only)</p>
                  <CodeBlock>pip install MetaTrader5 websockets python-dotenv</CodeBlock>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-[10px] font-bold text-gold bg-gold/10 rounded px-1.5 py-0.5 mt-0.5">3</span>
                <div className="flex-1 space-y-1">
                  <p className="text-xs text-text-secondary">Make sure MetaTrader 5 is open and logged in, then run:</p>
                  <CodeBlock>python backend/mt5_bridge.py --auto-trade</CodeBlock>
                  <p className="text-[10px] text-text-muted">Use this auto-trade bridge when you want orders to execute from signals.</p>
                </div>
              </div>
              <div className="rounded-xl bg-warning/5 border border-warning/20 p-3 mt-2">
                <p className="text-[10px] text-warning">
                  ⚠️ Enable algo trading in MT5: Tools → Options → Expert Advisors → Allow automated trading
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
