"use client";

import { useLivePrice } from "@/hooks/useLivePrice";
import { TrendingUp, TrendingDown, RefreshCw, Loader2 } from "lucide-react";

export default function LivePriceTicker() {
  const { data, loading, error, tick } = useLivePrice();

  const isPositive = (data?.change ?? 0) >= 0;
  const isAllTickFallback = data?.source === "ALLTICK";
  const isHttpPoll = data?.source === "http-poll";

  const priceColor =
    tick === "up"
      ? "text-bullish"
      : tick === "down"
      ? "text-bearish"
      : "text-gold-light";

  return (
    <div className="animate-fade-in-up mt-16 glass-gold rounded-2xl px-8 py-4" style={{ animationDelay: "400ms" }}>
      <div className="flex items-center gap-8">
        {/* Price */}
        <div className="text-center">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">
            XAU/USD
            {isAllTickFallback && <span className="text-gold/60 ml-1">(Backup)</span>}
            {isHttpPoll && <span className="text-gold/60 ml-1">(Polling)</span>}
          </p>
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-text-muted">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>Connecting to MT5...</span>
            </div>
          ) : error ? (
            <p className="text-sm text-gold flex items-center gap-1">
              <RefreshCw className="h-3 w-3" /> {error}
            </p>
          ) : (
            <p
              className={`text-2xl font-bold font-[family-name:var(--font-jetbrains-mono)] transition-colors duration-300 ${priceColor}`}
            >
              {data!.price.toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </p>
          )}
        </div>

        <div className="h-10 w-px bg-border" />

        {/* Change */}
        <div className="text-center">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Change</p>
          {loading ? (
            <div className="h-6 w-32 rounded-lg bg-surface animate-pulse" />
          ) : data ? (
            <div className="flex items-center gap-1">
              {isPositive ? (
                <TrendingUp className="h-4 w-4 text-bullish" />
              ) : (
                <TrendingDown className="h-4 w-4 text-bearish" />
              )}
              <p
                className={`text-lg font-semibold font-[family-name:var(--font-jetbrains-mono)] ${
                  isPositive ? "text-bullish" : "text-bearish"
                }`}
              >
                {isPositive ? "+" : ""}
                {data.change.toFixed(2)} ({isPositive ? "+" : ""}
                {data.changePercent.toFixed(2)}%)
              </p>
            </div>
          ) : null}
        </div>

        <div className="h-10 w-px bg-border hidden sm:block" />

        {/* Live dot */}
        <div className="text-center hidden sm:block">
          <p className="text-xs text-text-muted uppercase tracking-wider mb-1">Status</p>
          <div className="flex items-center justify-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute h-2 w-2 rounded-full bg-bullish/60" />
              <span className="relative h-2 w-2 rounded-full bg-bullish" />
            </span>
            <span className="text-xs font-medium text-bullish">Live</span>
          </div>
        </div>
      </div>
    </div>
  );
}
