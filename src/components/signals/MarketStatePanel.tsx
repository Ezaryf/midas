"use client";

import { useMidasStore } from "@/store/useMidasStore";
import type { MarketState } from "@/lib/types";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Gauge,
  Layers,
  Minus,
  Shield,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import { formatPrice } from "@/lib/utils";

const REGIME_DISPLAY: Record<
  string,
  { label: string; color: string; bg: string; border: string; icon: typeof Activity }
> = {
  breakout_up: { label: "BREAKOUT UP", color: "text-bullish", bg: "bg-bullish/10", border: "border-bullish/30", icon: ArrowUpRight },
  breakout_down: { label: "BREAKOUT DOWN", color: "text-bearish", bg: "bg-bearish/10", border: "border-bearish/30", icon: ArrowDownRight },
  trend_up: { label: "TREND UP", color: "text-bullish", bg: "bg-bullish/10", border: "border-bullish/20", icon: TrendingUp },
  trend_down: { label: "TREND DOWN", color: "text-bearish", bg: "bg-bearish/10", border: "border-bearish/20", icon: TrendingDown },
  range: { label: "RANGE", color: "text-warning", bg: "bg-warning/10", border: "border-warning/20", icon: Minus },
  reversal_up: { label: "REVERSAL UP", color: "text-gold", bg: "bg-gold/10", border: "border-gold/30", icon: ArrowUpRight },
  reversal_down: { label: "REVERSAL DOWN", color: "text-gold", bg: "bg-gold/10", border: "border-gold/30", icon: ArrowDownRight },
  neutral: { label: "NEUTRAL", color: "text-white/50", bg: "bg-white/5", border: "border-white/10", icon: Activity },
};

const STATE_FLOW = [
  { key: "compression", label: "Compression" },
  { key: "breakout", label: "Breakout" },
  { key: "impulse", label: "Impulse" },
  { key: "pullback", label: "Pullback" },
  { key: "continuation", label: "Continuation" },
  { key: "weakening", label: "Weakening" },
  { key: "range", label: "Range" },
];

function getActiveFlowStep(ms: MarketState): string {
  if (ms.phase_key) return ms.phase_key;
  if (ms.compression_ratio < 0.9 && ms.regime === "neutral") return "compression";
  if (ms.regime.startsWith("breakout")) return "breakout";
  if (ms.regime === "range") return "range";
  if (ms.regime.startsWith("reversal")) return "weakening";
  if (ms.recent_minor_high < ms.prior_minor_high && ms.ema_slope < 0) return "weakening";
  if (ms.regime.startsWith("trend") && ms.efficiency_ratio > 0.65 && ms.body_strength > 1.0) return "continuation";
  if (ms.regime.startsWith("trend") && ms.efficiency_ratio > 0.55) return "impulse";
  if (ms.regime.startsWith("trend")) return "pullback";
  return "compression";
}

function getSwingSequence(ms: MarketState): string[] {
  const tags: string[] = [];
  if (ms.recent_minor_high > ms.prior_minor_high) tags.push("HH");
  else if (ms.recent_minor_high < ms.prior_minor_high) tags.push("LH");
  else tags.push("EH");

  if (ms.recent_minor_low > ms.prior_minor_low) tags.push("HL");
  else if (ms.recent_minor_low < ms.prior_minor_low) tags.push("LL");
  else tags.push("EL");

  return tags;
}

function metricTone(value: number, thresholds: [number, number], inverse = false): string {
  const [low, high] = thresholds;
  if (inverse) {
    if (value <= low) return "text-bullish";
    if (value >= high) return "text-bearish";
    return "text-warning";
  }
  if (value >= high) return "text-bullish";
  if (value <= low) return "text-bearish";
  return "text-warning";
}

export default function MarketStatePanel() {
  const marketState = useMidasStore((state) => state.marketState);

  if (!marketState) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center rounded-lg border border-white/5 bg-[#131722] p-6 text-center">
        <Gauge className="mb-3 h-8 w-8 text-white/10" />
        <p className="text-xs font-bold uppercase tracking-wider text-white/30">
          Market State Engine
        </p>
        <p className="mt-2 text-[10px] text-white/15">Awaiting live market data to begin analysis...</p>
      </div>
    );
  }

  const ms = marketState;
  const regimeCfg = REGIME_DISPLAY[ms.regime] || REGIME_DISPLAY.neutral;
  const RegimeIcon = regimeCfg.icon;
  const activeStep = getActiveFlowStep(ms);
  const phaseLabel = ms.phase_label || STATE_FLOW.find((step) => step.key === activeStep)?.label || "Compression";
  const phaseDescription = ms.phase_description || "The engine is classifying price behavior through its state machine.";
  const swingSequence = getSwingSequence(ms);
  const priceToResistance = ms.resistance - ms.current_price;
  const priceToSupport = ms.current_price - ms.support;

  return (
    <div className="h-full w-full overflow-y-auto md:overflow-hidden rounded-lg border border-white/5 bg-[#131722] flex flex-col md:flex-row p-4 gap-4 md:gap-6 hide-scrollbar">
      
      {/* COLUMN 1: Primary Insight & Regime */}
      <div className="flex-[1.2] flex flex-col justify-between border-b md:border-b-0 md:border-r border-white/5 pb-4 md:pb-0 md:pr-6">
        
        {/* Header Block */}
        <div>
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className={`flex h-10 w-10 items-center justify-center rounded-xl border ${regimeCfg.bg} ${regimeCfg.border} shadow-lg backdrop-blur`}>
                <RegimeIcon className={`h-5 w-5 ${regimeCfg.color}`} />
              </div>
              <div className="flex flex-col">
                <span className={`text-sm font-black tracking-widest uppercase ${regimeCfg.color}`}>
                  {regimeCfg.label}
                </span>
                <div className="mt-1 flex items-center gap-2">
                  <span className="text-[10px] uppercase font-bold tracking-widest text-white/30 bg-black/30 px-1.5 py-0.5 rounded">
                    {ms.timeframe} · {ms.source}
                  </span>
                  <span className="text-[10px] uppercase font-bold tracking-widest text-gold/80 bg-gold/10 border border-gold/20 px-1.5 py-0.5 rounded">
                    {phaseLabel}
                  </span>
                </div>
              </div>
            </div>
            
            <div className="flex flex-col items-end pt-1">
              <span className={`text-xl leading-none font-bold font-['JetBrains_Mono'] ${regimeCfg.color}`}>
                {ms.regime_confidence.toFixed(0)}%
              </span>
              <span className="text-[9px] uppercase tracking-widest text-white/25 mt-1 font-bold">Confidence</span>
            </div>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-white/40 font-medium">
            {phaseDescription}
          </p>
        </div>

        {/* Actionable Tags */}
        <div className="mt-4">
          <p className="mb-2 text-[9px] font-bold uppercase tracking-widest text-white/20">Machine Insights</p>
          <div className="flex flex-wrap gap-1.5">
            {ms.notes.length > 0 ? (
              ms.notes.map((note) => (
                <span
                  key={note}
                  className="rounded-full border border-gold/20 bg-gold/10 px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-gold/80 shadow-[0_0_10px_rgba(245,158,11,0.05)]"
                >
                  {note.replaceAll("_", " ")}
                </span>
              ))
            ) : (
              <span className="text-[10px] text-white/20 italic">No specific conditions met.</span>
            )}
          </div>
        </div>
      </div>

      {/* COLUMN 2: Structure Metrics */}
      <div className="flex-1 flex flex-col justify-between border-b md:border-b-0 md:border-r border-white/5 pb-4 md:pb-0 md:pr-6">
        <div>
          <p className="mb-3 text-[9px] font-bold uppercase tracking-widest text-white/30 flex items-center gap-1.5">
            <Gauge className="h-3 w-3" /> Core Metrics
          </p>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "ATR", value: ms.atr.toFixed(2), icon: Activity, tone: "text-white" },
              { label: "Compression", value: `${ms.compression_ratio.toFixed(2)}x`, icon: Layers, tone: metricTone(ms.compression_ratio, [0.85, 1.15], true) },
              { label: "Efficiency", value: `${(ms.efficiency_ratio * 100).toFixed(0)}%`, icon: Gauge, tone: metricTone(ms.efficiency_ratio, [0.3, 0.55]) },
              { label: "Rel Volume", value: `${ms.relative_volume.toFixed(2)}x`, icon: BarChart3, tone: metricTone(ms.relative_volume, [0.8, 1.25]) },
              { label: "Body Strength", value: `${ms.body_strength.toFixed(2)}x`, icon: Zap, tone: metricTone(ms.body_strength, [0.7, 1.1]) },
              {
                label: "EMA Slope",
                value: ms.ema_slope > 0 ? `+${ms.ema_slope.toFixed(2)}` : ms.ema_slope.toFixed(2),
                icon: ms.ema_slope >= 0 ? TrendingUp : TrendingDown,
                tone: ms.ema_slope > 0 ? "text-bullish" : ms.ema_slope < 0 ? "text-bearish" : "text-white/50",
              },
            ].map(({ label, value, icon: Icon, tone }) => (
              <div key={label} className="flex flex-col rounded-md border border-white/5 bg-black/40 p-2 relative overflow-hidden group">
                {/* Subtle highlight */}
                <div className="absolute inset-0 bg-white/5 opacity-0 group-hover:opacity-100 transition-opacity" />
                <div className="mb-1.5 flex items-center gap-1.5 relative z-10 w-full overflow-hidden">
                  <Icon className="h-3 w-3 text-white/20 shrink-0" />
                  <span className="text-[8px] font-bold uppercase tracking-widest text-white/30">
                    {label}
                  </span>
                </div>
                <span className={`text-xs font-black font-['JetBrains_Mono'] relative z-10 ${tone}`}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* COLUMN 3: Key Levels & Swings */}
      <div className="flex-1 flex flex-col justify-between min-w-0">
        <div>
          <p className="mb-3 text-[9px] font-bold uppercase tracking-widest text-white/30 flex items-center gap-1.5">
            <Shield className="h-3 w-3" /> Structure Profile
          </p>
          <div className="space-y-2">
            {[
              { label: "Resistance", price: ms.resistance, dist: priceToResistance, color: "text-bearish", barColor: "bg-bearish", border: "border-bearish/20", bg: "bg-bearish/5" },
              { label: "Support", price: ms.support, dist: priceToSupport, color: "text-bullish", barColor: "bg-bullish", border: "border-bullish/20", bg: "bg-bullish/5" },
            ].map(({ label, price, dist, color, barColor, border, bg }) => {
              const pct = Math.min(Math.abs(dist) / Math.max(ms.range_width, 0.01), 1);
              return (
                <div key={label} className={`rounded-lg border ${border} ${bg} p-2.5`}>
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className={`text-[9px] font-bold uppercase tracking-widest ${color}`}>
                      {label}
                    </span>
                    <span className={`text-[11px] font-bold font-['JetBrains_Mono'] ${color}`}>
                      {formatPrice(price)}
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/40">
                    <div className={`h-full rounded-full shadow-[0_0_8px_rgba(currentColor)] ${barColor}`} style={{ width: `${(1 - pct) * 100}%` }} />
                  </div>
                  <div className="mt-1 flex justify-between">
                    <span className="text-[9px] text-white/30 font-['JetBrains_Mono']">{Math.abs(dist).toFixed(2)} pts away</span>
                    <span className="text-[8px] text-white/20 uppercase tracking-wider font-bold">
                      {ms.regime === "range" ? `Touches: ${label === "Resistance" ? ms.boundary_touches_high : ms.boundary_touches_low}` : ""}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer info: Swing & Close Location */}
        <div className="mt-4 flex flex-col gap-2">
          {/* Swings */}
          <div className="flex items-center justify-between rounded bg-black/30 px-2 py-1.5 border border-white/5">
            <span className="text-[8px] font-bold uppercase tracking-widest text-white/30">
              Swings
            </span>
            <div className="flex items-center gap-1">
              {swingSequence.map((tag, i) => {
                const isBull = tag === "HH" || tag === "HL";
                const isBear = tag === "LH" || tag === "LL";
                return (
                  <span
                    key={`${tag}-${i}`}
                    className={`rounded-[3px] px-1.5 py-0.5 text-[9px] font-bold font-['JetBrains_Mono'] ${
                      isBull
                        ? "bg-bullish/15 text-bullish shadow-[0_0_5px_rgba(34,197,94,0.1)]"
                        : isBear
                        ? "bg-bearish/15 text-bearish shadow-[0_0_5px_rgba(239,68,68,0.1)]"
                        : "bg-white/10 text-white/40"
                    }`}
                  >
                    {tag}
                  </span>
                );
              })}
            </div>
          </div>
          {/* Close Location */}
          <div className="flex items-center justify-between rounded bg-black/30 px-2 py-1.5 border border-white/5 relative overflow-hidden">
             <span className="text-[8px] font-bold uppercase tracking-widest text-white/30 z-10">
              Bar Close
            </span>
            <div className="absolute inset-y-0 right-0 w-24 bg-black/50 z-0 backdrop-blur-sm" />
            <div className="flex items-center justify-end w-32 relative z-10">
              <div className="relative h-1.5 w-full rounded-full bg-white/10 mr-2">
                <div
                  className="absolute h-full rounded-full shadow-lg"
                  style={{
                    width: `${ms.close_location * 100}%`,
                    background: "linear-gradient(90deg, #ef4444, #f59e0b, #22c55e)",
                  }}
                />
              </div>
              <span className="text-[9px] font-bold font-['JetBrains_Mono'] text-white/70 min-w-[28px] text-right">
                {(ms.close_location * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>
      </div>
      
    </div>
  );
}
