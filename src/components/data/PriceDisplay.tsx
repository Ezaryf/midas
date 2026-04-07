"use client";

import { Activity, TrendingUp, TrendingDown } from "lucide-react";
import { useLivePrice } from "@/hooks/useLivePrice";

// Props are optional — component fetches live data itself,
// but accepts overrides from the WebSocket store when connected.
interface PriceDisplayProps {
  bid?: number;
  ask?: number;
  spread?: number;
  change?: number;
  changePercent?: number;
  high24h?: number;
  low24h?: number;
}

export default function PriceDisplay(props: PriceDisplayProps) {
  const { data: live, loading, tick } = useLivePrice();

  // Live data always wins — props only used as last-resort fallback
  // (e.g. when MT5 WebSocket sends richer data than the polling API)
  const bid           = live?.bid           ?? props.bid           ?? 0;
  const ask           = live?.ask           ?? props.ask           ?? 0;
  const spread        = live?.price != null ? (ask - bid)          : props.spread ?? 0;
  const change        = live?.change        ?? props.change        ?? 0;
  const changePercent = live?.changePercent ?? props.changePercent ?? 0;
  const high24h       = live?.high          ?? props.high24h       ?? bid;
  const low24h        = live?.low           ?? props.low24h        ?? bid;

  const isPositive = change >= 0;

  const priceColor =
    tick === "up"
      ? "text-bullish"
      : tick === "down"
      ? "text-bearish"
      : "text-gold-light";

  return (
    <div className="glass-gold rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Activity className="h-4 w-4 text-gold" />
        <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">
          XAU/USD Live
        </span>
        <span className="ml-auto flex h-2 w-2">
          <span className="animate-ping absolute h-2 w-2 rounded-full bg-bullish/60" />
          <span className="relative h-2 w-2 rounded-full bg-bullish" />
        </span>
      </div>

      {/* Main Price */}
      {loading && !bid ? (
        <div className="h-9 w-36 rounded-lg bg-surface animate-pulse mb-3" />
      ) : (
        <div className="flex items-baseline gap-3 mb-3">
          <span
            className={`text-3xl font-bold font-[family-name:var(--font-jetbrains-mono)] transition-colors duration-300 ${priceColor}`}
          >
            {bid.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
          <div className="flex items-center gap-1">
            {isPositive ? (
              <TrendingUp className="h-4 w-4 text-bullish" />
            ) : (
              <TrendingDown className="h-4 w-4 text-bearish" />
            )}
            <span
              className={`text-sm font-semibold font-[family-name:var(--font-jetbrains-mono)] ${
                isPositive ? "text-bullish" : "text-bearish"
              }`}
            >
              {isPositive ? "+" : ""}
              {change.toFixed(2)} ({isPositive ? "+" : ""}
              {changePercent.toFixed(2)}%)
            </span>
          </div>
        </div>
      )}

      {/* Bid/Ask/High/Low */}
      <div className="grid grid-cols-4 gap-3">
        <div>
          <span className="text-[10px] text-text-muted uppercase tracking-wider">Bid</span>
          <p className="text-xs font-medium font-[family-name:var(--font-jetbrains-mono)]">
            {bid.toFixed(2)}
          </p>
        </div>
        <div>
          <span className="text-[10px] text-text-muted uppercase tracking-wider">Ask</span>
          <p className="text-xs font-medium font-[family-name:var(--font-jetbrains-mono)]">
            {ask.toFixed(2)}
          </p>
        </div>
        <div>
          <span className="text-[10px] text-text-muted uppercase tracking-wider">24H High</span>
          <p className="text-xs font-medium font-[family-name:var(--font-jetbrains-mono)] text-bullish">
            {high24h.toFixed(2)}
          </p>
        </div>
        <div>
          <span className="text-[10px] text-text-muted uppercase tracking-wider">24H Low</span>
          <p className="text-xs font-medium font-[family-name:var(--font-jetbrains-mono)] text-bearish">
            {low24h.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Spread */}
      <div className="mt-3 pt-3 border-t border-border">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-text-muted">
            Spread: {spread.toFixed(2)} pts
          </span>
          <span className="text-[10px] text-text-muted">
            {spread < 0.5 ? "🟢 Tight" : spread < 1 ? "🟡 Normal" : "🔴 Wide"}
          </span>
        </div>
      </div>
    </div>
  );
}
