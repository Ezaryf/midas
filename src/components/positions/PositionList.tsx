"use client";

import { ArrowUpRight, ArrowDownRight, Clock, DollarSign } from "lucide-react";
import { formatPrice, formatRelativeTime } from "@/lib/utils";
import type { Position } from "@/hooks/usePositions";

interface PositionListProps {
  positions: Position[];
}

export default function PositionList({ positions }: PositionListProps) {
  if (positions.length === 0) {
    return (
      <div className="rounded-xl bg-surface/50 border border-border p-6 text-center">
        <p className="text-sm text-text-muted">No open positions</p>
      </div>
    );
  }

  const totalProfit = positions.reduce((sum, p) => sum + p.profit, 0);

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="rounded-xl bg-surface/50 border border-border p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-text-muted mb-1">Open Positions</p>
            <p className="text-2xl font-bold font-[family-name:var(--font-jetbrains-mono)]">
              {positions.length}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-text-muted mb-1">Total P/L</p>
            <p className={`text-2xl font-bold font-[family-name:var(--font-jetbrains-mono)] ${
              totalProfit >= 0 ? "text-bullish" : "text-bearish"
            }`}>
              {totalProfit >= 0 ? "+" : ""}{totalProfit.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {/* Position Cards */}
      {positions.map((position) => {
        const isBuy = position.type.toUpperCase().includes("BUY");
        const isProfit = position.profit >= 0;
        const openTime = new Date(position.open_time);

        return (
          <div
            key={position.ticket}
            className="rounded-xl bg-surface border border-border p-4 hover:border-gold/30 transition-colors"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${
                  isBuy ? "bg-bullish/10 border border-bullish/20" : "bg-bearish/10 border border-bearish/20"
                }`}>
                  {isBuy ? (
                    <ArrowUpRight className="h-4 w-4 text-bullish" />
                  ) : (
                    <ArrowDownRight className="h-4 w-4 text-bearish" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-bold ${isBuy ? "text-bullish" : "text-bearish"}`}>
                      {position.type}
                    </span>
                    <span className="text-xs text-text-muted">{position.symbol}</span>
                  </div>
                  <p className="text-[10px] text-text-muted">
                    Ticket #{position.ticket} · {position.volume} lots
                  </p>
                </div>
              </div>
              
              <div className="text-right">
                <p className={`text-lg font-bold font-[family-name:var(--font-jetbrains-mono)] ${
                  isProfit ? "text-bullish" : "text-bearish"
                }`}>
                  {isProfit ? "+" : ""}{position.profit.toFixed(2)}
                </p>
                <p className="text-[10px] text-text-muted">P/L</p>
              </div>
            </div>

            {/* Price Levels */}
            <div className="grid grid-cols-3 gap-2 mb-3">
              <div className="rounded-lg bg-surface-active p-2">
                <p className="text-[9px] text-text-muted uppercase mb-0.5">Entry</p>
                <p className="text-xs font-bold font-[family-name:var(--font-jetbrains-mono)]">
                  {formatPrice(position.open_price)}
                </p>
              </div>
              <div className="rounded-lg bg-surface-active p-2">
                <p className="text-[9px] text-text-muted uppercase mb-0.5">Current</p>
                <p className="text-xs font-bold font-[family-name:var(--font-jetbrains-mono)] text-gold">
                  {formatPrice(position.current_price)}
                </p>
              </div>
              <div className="rounded-lg bg-surface-active p-2">
                <p className="text-[9px] text-text-muted uppercase mb-0.5">SL / TP</p>
                <p className="text-xs font-bold font-[family-name:var(--font-jetbrains-mono)]">
                  {position.sl > 0 ? formatPrice(position.sl) : "-"} / {position.tp > 0 ? formatPrice(position.tp) : "-"}
                </p>
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between text-[10px] text-text-muted">
              <div className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                <span>{formatRelativeTime(openTime)}</span>
              </div>
              {position.comment && (
                <span className="truncate max-w-[200px]">{position.comment}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
