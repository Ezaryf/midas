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
      <div className="flex flex-col items-center justify-center rounded-lg border border-white/5 bg-[#131722] p-4 text-center">
        <Gauge className="mb-2 h-5 w-5 text-white/10" />
        <p className="text-[10px] font-medium uppercase tracking-wider text-white/30">
          Market State Engine
        </p>
        <p className="mt-1 text-[9px] text-white/15">Waiting for first analysis cycle...</p>
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
    <div className="overflow-hidden rounded-lg border border-white/5 bg-[#131722]">
      <div className={`flex items-center justify-between border-b px-3 py-2.5 ${regimeCfg.bg} ${regimeCfg.border}`}>
        <div className="flex items-center gap-2">
          <div className={`flex h-6 w-6 items-center justify-center rounded-md border ${regimeCfg.bg} ${regimeCfg.border}`}>
            <RegimeIcon className={`h-3.5 w-3.5 ${regimeCfg.color}`} />
          </div>
          <div>
            <span className={`text-[11px] font-bold tracking-wider ${regimeCfg.color}`}>
              {regimeCfg.label}
            </span>
            <div className="mt-0.5 flex items-center gap-1.5">
              <span className="text-[8px] uppercase tracking-widest text-white/30">
                {ms.timeframe} · {ms.source}
              </span>
              <span className="text-[8px] uppercase tracking-widest text-gold/70">
                {phaseLabel}
              </span>
            </div>
          </div>
        </div>
        <div className="flex flex-col items-end">
          <span className={`text-xs font-bold font-[family-name:var(--font-jetbrains-mono)] ${regimeCfg.color}`}>
            {ms.regime_confidence.toFixed(0)}%
          </span>
          <span className="text-[8px] text-white/25">confidence</span>
        </div>
      </div>

      <div className="space-y-3 p-3">
        <div>
          <p className="mb-1.5 text-[8px] font-bold uppercase tracking-widest text-white/25">
            Market Phase
          </p>
          <div className="flex items-center gap-0.5">
            {STATE_FLOW.map((step, index) => {
              const isActive = step.key === activeStep;
              const isPast = STATE_FLOW.findIndex((item) => item.key === activeStep) > index;
              return (
                <div key={step.key} className="flex flex-1 flex-col items-center">
                  <div
                    className={`h-1 w-full rounded-full transition-all duration-500 ${
                      isActive
                        ? "bg-gold shadow-[0_0_6px_rgba(245,158,11,0.4)]"
                        : isPast
                        ? "bg-white/15"
                        : "bg-white/5"
                    }`}
                  />
                  <span className={`mt-1 text-[7px] tracking-wide ${isActive ? "font-bold text-gold" : "text-white/20"}`}>
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="mt-1.5 text-[9px] leading-relaxed text-white/35">
            {phaseDescription}
          </p>
        </div>

        <div>
          <p className="mb-1.5 text-[8px] font-bold uppercase tracking-widest text-white/25">
            Structure Metrics
          </p>
          <div className="grid grid-cols-3 gap-1.5">
            {[
              { label: "ATR", value: ms.atr.toFixed(2), icon: Activity, tone: "text-white/80" },
              { label: "Compression", value: `${ms.compression_ratio.toFixed(2)}x`, icon: Layers, tone: metricTone(ms.compression_ratio, [0.85, 1.15], true) },
              { label: "Efficiency", value: `${(ms.efficiency_ratio * 100).toFixed(0)}%`, icon: Gauge, tone: metricTone(ms.efficiency_ratio, [0.3, 0.55]) },
              { label: "Rel. Volume", value: `${ms.relative_volume.toFixed(2)}x`, icon: BarChart3, tone: metricTone(ms.relative_volume, [0.8, 1.25]) },
              { label: "Body Str.", value: `${ms.body_strength.toFixed(2)}x`, icon: Zap, tone: metricTone(ms.body_strength, [0.7, 1.1]) },
              {
                label: "EMA Slope",
                value: ms.ema_slope > 0 ? `+${ms.ema_slope.toFixed(2)}` : ms.ema_slope.toFixed(2),
                icon: ms.ema_slope >= 0 ? TrendingUp : TrendingDown,
                tone: ms.ema_slope > 0 ? "text-bullish" : ms.ema_slope < 0 ? "text-bearish" : "text-white/50",
              },
            ].map(({ label, value, icon: Icon, tone }) => (
              <div key={label} className="flex flex-col rounded-md border border-white/5 bg-black/30 p-1.5">
                <div className="mb-0.5 flex items-center gap-1">
                  <Icon className="h-2.5 w-2.5 text-white/20" />
                  <span className="truncate text-[7px] font-bold uppercase tracking-widest text-white/25">
                    {label}
                  </span>
                </div>
                <span className={`text-[10px] font-bold font-[family-name:var(--font-jetbrains-mono)] ${tone}`}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="mb-1.5 text-[8px] font-bold uppercase tracking-widest text-white/25">
            Key Levels
          </p>
          <div className="space-y-1">
            {[
              { label: "Resistance", price: ms.resistance, dist: priceToResistance, color: "text-bearish", barColor: "bg-bearish/40" },
              { label: "Support", price: ms.support, dist: priceToSupport, color: "text-bullish", barColor: "bg-bullish/40" },
            ].map(({ label, price, dist, color, barColor }) => {
              const pct = Math.min(Math.abs(dist) / Math.max(ms.range_width, 0.01), 1);
              return (
                <div key={label} className="rounded border border-white/5 bg-black/20 px-2 py-1.5">
                  <div className="mb-1 flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Shield className={`h-2.5 w-2.5 ${color}`} />
                      <span className="text-[8px] font-bold uppercase tracking-widest text-white/30">
                        {label}
                      </span>
                    </div>
                    <span className={`text-[10px] font-bold font-[family-name:var(--font-jetbrains-mono)] ${color}`}>
                      {formatPrice(price)}
                    </span>
                  </div>
                  <div className="h-1 w-full overflow-hidden rounded-full bg-white/5">
                    <div className={`h-full rounded-full ${barColor}`} style={{ width: `${(1 - pct) * 100}%` }} />
                  </div>
                  <div className="mt-0.5 flex justify-between">
                    <span className="text-[7px] text-white/20">{Math.abs(dist).toFixed(2)} pts away</span>
                    <span className="text-[7px] text-white/15">
                      {ms.regime === "range" ? `Touches: ${label === "Resistance" ? ms.boundary_touches_high : ms.boundary_touches_low}` : ""}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-between rounded border border-white/5 bg-black/20 px-2 py-1.5">
          <div className="flex items-center gap-1.5">
            <Activity className="h-2.5 w-2.5 text-white/20" />
            <span className="text-[8px] font-bold uppercase tracking-widest text-white/25">
              Swing Structure
            </span>
          </div>
          <div className="flex items-center gap-1">
            {swingSequence.map((tag) => {
              const isBull = tag === "HH" || tag === "HL";
              const isBear = tag === "LH" || tag === "LL";
              return (
                <span
                  key={tag}
                  className={`rounded px-1 py-0.5 text-[9px] font-bold font-[family-name:var(--font-jetbrains-mono)] ${
                    isBull
                      ? "border border-bullish/20 bg-bullish/10 text-bullish"
                      : isBear
                      ? "border border-bearish/20 bg-bearish/10 text-bearish"
                      : "border border-white/10 bg-white/5 text-white/40"
                  }`}
                >
                  {tag}
                </span>
              );
            })}
          </div>
        </div>

        {ms.notes.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {ms.notes.map((note) => (
              <span
                key={note}
                className="rounded-full border border-gold/15 bg-gold/10 px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wider text-gold/70"
              >
                {note.replaceAll("_", " ")}
              </span>
            ))}
          </div>
        )}

        <div className="rounded border border-white/5 bg-black/20 px-2 py-1.5">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[8px] font-bold uppercase tracking-widest text-white/25">
              Close Location
            </span>
            <span className="text-[9px] font-bold font-[family-name:var(--font-jetbrains-mono)] text-white/60">
              {(ms.close_location * 100).toFixed(0)}%
            </span>
          </div>
          <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-white/5">
            <div
              className="absolute h-full rounded-full transition-all duration-500"
              style={{
                width: `${ms.close_location * 100}%`,
                background: "linear-gradient(90deg, hsl(0,70%,55%), hsl(45,80%,55%), hsl(120,60%,45%))",
              }}
            />
          </div>
          <div className="mt-0.5 flex justify-between">
            <span className="text-[7px] text-white/15">Low</span>
            <span className="text-[7px] text-white/15">High</span>
          </div>
        </div>
      </div>
    </div>
  );
}
