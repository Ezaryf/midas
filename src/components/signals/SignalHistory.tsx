"use client";

import type { TradeSignal } from "@/lib/types";
import {
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  XCircle,
  Clock,
  Minus,
} from "lucide-react";
import { formatPrice, formatRelativeTime } from "@/lib/utils";

interface SignalHistoryProps {
  signals: TradeSignal[];
}

const statusConfig = {
  PENDING: { label: "Pending", icon: Clock, color: "text-text-muted", bg: "bg-surface" },
  ACTIVE: { label: "Active", icon: Clock, color: "text-info", bg: "bg-info/10" },
  HIT_TP1: { label: "TP1 Hit", icon: CheckCircle2, color: "text-bullish", bg: "bg-bullish/10" },
  HIT_TP2: { label: "TP2 Hit", icon: CheckCircle2, color: "text-bullish", bg: "bg-bullish/10" },
  STOPPED: { label: "Stopped", icon: XCircle, color: "text-bearish", bg: "bg-bearish/10" },
  EXPIRED: { label: "Expired", icon: Clock, color: "text-text-muted", bg: "bg-surface" },
};

export default function SignalHistory({ signals }: SignalHistoryProps) {
  return (
    <div className="space-y-2">
      {signals.map((signal, i) => {
        const status = signal.status ? statusConfig[signal.status] : statusConfig.PENDING;
        const StatusIcon = status.icon;
        const isBuy = signal.direction === "BUY";
        const isHold = signal.direction === "HOLD";
        const timestamp = signal.timestamp ? new Date(signal.timestamp) : new Date();

        return (
          <div
            key={`${signal.id || signal.timestamp || i}-${i}`}
            className="flex items-center justify-between rounded-xl bg-surface/50 hover:bg-surface px-4 py-3 transition-colors"
          >
            {/* Direction + Price */}
            <div className="flex items-center gap-3">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-lg ${
                  isHold
                    ? "bg-warning/10 border border-warning/20"
                    : isBuy
                    ? "bg-bullish/10 border border-bullish/20"
                    : "bg-bearish/10 border border-bearish/20"
                }`}
              >
                {isHold ? (
                  <Minus className="h-4 w-4 text-warning" />
                ) : isBuy ? (
                  <ArrowUpRight className="h-4 w-4 text-bullish" />
                ) : (
                  <ArrowDownRight className="h-4 w-4 text-bearish" />
                )}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs font-bold ${
                      isHold ? "text-warning" : isBuy ? "text-bullish" : "text-bearish"
                    }`}
                  >
                    {signal.direction}
                  </span>
                  <span className="text-[10px] text-text-muted px-1.5 py-0.5 rounded-md bg-surface border border-white/5">
                    {(signal.symbol || "XAUUSD").toUpperCase()}
                  </span>
                  {!isHold && (
                    <span className="text-xs font-medium font-(family-name:--font-jetbrains-mono)">
                      @ {formatPrice(signal.entry_price)}
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-text-muted">
                  {formatRelativeTime(timestamp)} · {signal.trading_style}
                </p>
              </div>
            </div>

            {/* Status + Outcome */}
            <div className="flex items-center gap-3">
              {signal.outcome !== undefined && signal.outcome !== null && (
                <span
                  className={`text-xs font-bold font-(family-name:--font-jetbrains-mono) ${
                    signal.outcome >= 0 ? "text-bullish" : "text-bearish"
                  }`}
                >
                  {signal.outcome >= 0 ? "+" : ""}
                  {formatPrice(signal.outcome)}
                </span>
              )}
              <div className={`flex items-center gap-1 rounded-lg px-2 py-1 ${status.bg}`}>
                <StatusIcon className={`h-3 w-3 ${status.color}`} />
                <span className={`text-[10px] font-medium ${status.color}`}>
                  {status.label}
                </span>
              </div>
            </div>
          </div>
        );
      })}

      {signals.length === 0 && (
        <div className="text-center py-8">
          <p className="text-sm text-text-muted">No signal history yet</p>
        </div>
      )}
    </div>
  );
}
