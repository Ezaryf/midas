"use client";

import {
  ArrowUpRight,
  ArrowDownRight,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Target,
  ShieldAlert,
  TrendingUp,
  Zap,
  Loader2,
} from "lucide-react";
import { useState } from "react";
import type { TradeSignal } from "@/lib/types";
import {
  formatPrice,
  formatConfidence,
  getRiskReward,
  calculatePips,
  formatRelativeTime,
} from "@/lib/utils";

interface SignalCardProps {
  signal: TradeSignal;
  onExecute?: () => Promise<{ status: string; message: string }>;
}

export default function SignalCard({ signal, onExecute }: SignalCardProps) {
  const [copied, setCopied]       = useState(false);
  const [expanded, setExpanded]   = useState(false);
  const [executing, setExecuting] = useState(false);
  const [execResult, setExecResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const timestamp = signal.timestamp ? new Date(signal.timestamp) : new Date();
  const isBuy   = signal.direction === "BUY";
  const isHold  = signal.direction === "HOLD";

  const handleCopy = () => {
    const symbol = (signal.symbol || "XAU/USD").toUpperCase();
    const text = `${signal.direction} ${symbol} @ ${formatPrice(signal.entry_price)}
SL: ${formatPrice(signal.stop_loss)}
TP1: ${formatPrice(signal.take_profit_1)}
TP2: ${formatPrice(signal.take_profit_2)}
Confidence: ${formatConfidence(signal.confidence)}
Reasoning: ${signal.reasoning}`;

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleExecute = async () => {
    if (!onExecute) return;
    setExecuting(true);
    setExecResult(null);
    try {
      const result = await onExecute();
      const isSuccess = result.status === "ok";
      
      setExecResult({ 
        ok: isSuccess, 
        msg: result.message || (isSuccess ? "Order executed" : "Execution failed")
      });
      
      // Keep success messages longer, errors shorter
      setTimeout(() => setExecResult(null), isSuccess ? 6000 : 5000);
    } catch (err) {
      setExecResult({ 
        ok: false, 
        msg: err instanceof Error ? err.message : "Network error — check backend connection" 
      });
      setTimeout(() => setExecResult(null), 5000);
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="relative rounded-2xl overflow-hidden glass">
      {/* Active beam effect */}
      {signal.status === "ACTIVE" && (
        <div className="absolute inset-0 rounded-2xl beam-border" />
      )}

      <div className="relative p-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div
              className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                isHold
                  ? "bg-warning/10 border border-warning/20"
                  : isBuy
                  ? "bg-bullish/10 border border-bullish/20"
                  : "bg-bearish/10 border border-bearish/20"
              }`}
            >
              {isHold ? (
                <Target className="h-5 w-5 text-warning" />
              ) : isBuy ? (
                <ArrowUpRight className="h-5 w-5 text-bullish" />
              ) : (
                <ArrowDownRight className="h-5 w-5 text-bearish" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span
                  className={`text-sm font-bold ${
                    isHold
                      ? "text-warning"
                      : isBuy
                      ? "text-bullish"
                      : "text-bearish"
                  }`}
                >
                  {signal.direction}
                </span>
                <span className="text-xs text-text-muted">{(signal.symbol || "XAU/USD").toUpperCase()}</span>
                <span className="text-[10px] text-text-muted bg-surface px-1.5 py-0.5 rounded-md">
                  {signal.trading_style}
                </span>
              </div>
              <p className="text-xs text-text-muted">
                {formatRelativeTime(timestamp)}
              </p>
            </div>
          </div>

          {/* Confidence Badge */}
          <div className="relative flex items-center justify-center w-12 h-12">
            <svg className="w-12 h-12 -rotate-90" viewBox="0 0 48 48">
              <circle
                cx="24"
                cy="24"
                r="20"
                fill="none"
                stroke="rgba(39,39,42,0.5)"
                strokeWidth="3"
              />
              <circle
                cx="24"
                cy="24"
                r="20"
                fill="none"
                stroke={
                  signal.confidence >= 75
                    ? "#22C55E"
                    : signal.confidence >= 50
                    ? "#F59E0B"
                    : "#EF4444"
                }
                strokeWidth="3"
                strokeDasharray={`${(signal.confidence / 100) * 125.6} 125.6`}
                strokeLinecap="round"
              />
            </svg>
            <span className="absolute text-xs font-bold font-(family-name:--font-jetbrains-mono)">
              {Math.round(signal.confidence)}
            </span>
          </div>
        </div>

        {/* Price Levels — hidden for HOLD */}
        {!isHold && (
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="rounded-xl bg-surface p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <Target className="h-3 w-3 text-gold" />
                <span className="text-[10px] uppercase tracking-wider text-text-muted">
                  Entry
                </span>
              </div>
              <p className="text-sm font-bold font-(family-name:--font-jetbrains-mono) text-gold-light">
                {formatPrice(signal.entry_price)}
              </p>
            </div>
            <div className="rounded-xl bg-surface p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <ShieldAlert className="h-3 w-3 text-bearish" />
                <span className="text-[10px] uppercase tracking-wider text-text-muted">
                  Stop Loss
                </span>
              </div>
              <p className="text-sm font-bold font-(family-name:--font-jetbrains-mono) text-bearish">
                {formatPrice(signal.stop_loss)}
              </p>
            </div>
            <div className="rounded-xl bg-surface p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <TrendingUp className="h-3 w-3 text-bullish" />
                <span className="text-[10px] uppercase tracking-wider text-text-muted">
                  TP1
                </span>
              </div>
              <p className="text-sm font-bold font-(family-name:--font-jetbrains-mono) text-bullish">
                {formatPrice(signal.take_profit_1)}
              </p>
              <p className="text-[10px] text-text-muted mt-0.5">
                {calculatePips(signal.entry_price, signal.take_profit_1)} pips ·{" "}
                RR {getRiskReward(signal.entry_price, signal.stop_loss, signal.take_profit_1)}
              </p>
            </div>
            <div className="rounded-xl bg-surface p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <TrendingUp className="h-3 w-3 text-bullish" />
                <span className="text-[10px] uppercase tracking-wider text-text-muted">
                  TP2
                </span>
              </div>
              <p className="text-sm font-bold font-(family-name:--font-jetbrains-mono) text-bullish">
                {formatPrice(signal.take_profit_2)}
              </p>
              <p className="text-[10px] text-text-muted mt-0.5">
                {calculatePips(signal.entry_price, signal.take_profit_2)} pips ·{" "}
                RR {getRiskReward(signal.entry_price, signal.stop_loss, signal.take_profit_2)}
              </p>
            </div>
          </div>
        )}

        {/* Reasoning Toggle */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between rounded-xl bg-surface px-3 py-2 text-xs text-text-secondary hover:bg-surface-hover transition-colors mb-3"
        >
          <span>💡 Why this trade?</span>
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </button>

        {expanded && (
          <div className="space-y-3 mb-3 animate-fade-in">
            <div className="rounded-xl bg-surface/50 p-3">
              <p className="text-xs text-text-secondary leading-relaxed">
                {signal.reasoning}
              </p>
            </div>
            
            {/* Patterns Section */}
            {"patterns" in signal && signal.patterns && Array.isArray(signal.patterns) && signal.patterns.length > 0 && (
              <div className="rounded-xl bg-surface/50 border border-gold/20 p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Zap className="h-3.5 w-3.5 text-gold" />
                  <span className="text-xs font-semibold text-gold">Detected Patterns</span>
                </div>
                <div className="space-y-1.5">
                  {signal.patterns.slice(0, 3).map((pattern: { type: string; confidence: number; description: string }, i: number) => (
                    <div key={i} className="flex items-start justify-between gap-2 text-[10px]">
                      <span className="text-text-muted flex-1">{pattern.type}</span>
                      <span className="font-bold font-[family-name:var(--font-jetbrains-mono)] text-gold shrink-0">
                        {pattern.confidence.toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col gap-2">
          <div className="flex gap-2">
            {!isHold && onExecute && (
              <button
                onClick={handleExecute}
                disabled={executing}
                className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-linear-to-r from-gold-dark via-gold to-gold-light px-4 py-2.5 text-sm font-semibold text-background hover:shadow-lg hover:shadow-gold/20 transition-all active:scale-[0.98] disabled:opacity-60 disabled:pointer-events-none"
              >
                {executing ? (
                  <><Loader2 className="h-4 w-4 animate-spin" />Sending...</>
                ) : (
                  <><Zap className="h-4 w-4" />Execute on MT5</>
                )}
              </button>
            )}
            <button
              onClick={handleCopy}
              className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-gold/10 border border-gold/20 px-4 py-2.5 text-sm font-medium text-gold hover:bg-gold/20 transition-all active:scale-[0.98]"
            >
              {copied ? <><Check className="h-4 w-4" />Copied!</> : <><Copy className="h-4 w-4" />Copy</>}
            </button>
          </div>
          {execResult && (
            <div className={`rounded-xl px-3 py-2 text-xs text-center font-medium ${execResult.ok ? "bg-bullish/10 text-bullish border border-bullish/20" : "bg-bearish/10 text-bearish border border-bearish/20"}`}>
              {execResult.ok ? "✅" : "⚠️"} {execResult.msg}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
