"use client";

import { useMidasStore } from "@/store/useMidasStore";
import type { MarketState } from "@/lib/types";
import {
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Zap,
  Gauge,
  BarChart3,
  Layers,
  Shield,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { formatPrice } from "@/lib/utils";

/* ─── Regime Config ─── */
const REGIME_DISPLAY: Record<
  string,
  { label: string; color: string; bg: string; border: string; icon: typeof Activity }
> = {
  breakout_up:    { label: "BREAKOUT ↑",    color: "text-bullish",  bg: "bg-bullish/10",  border: "border-bullish/30", icon: ArrowUpRight },
  breakout_down:  { label: "BREAKOUT ↓",    color: "text-bearish",  bg: "bg-bearish/10",  border: "border-bearish/30", icon: ArrowDownRight },
  trend_up:       { label: "TREND ↑",       color: "text-bullish",  bg: "bg-bullish/10",  border: "border-bullish/20", icon: TrendingUp },
  trend_down:     { label: "TREND ↓",       color: "text-bearish",  bg: "bg-bearish/10",  border: "border-bearish/20", icon: TrendingDown },
  range:          { label: "RANGE",          color: "text-warning",  bg: "bg-warning/10",  border: "border-warning/20", icon: Minus },
  reversal_up:    { label: "REVERSAL ↑",    color: "text-gold",     bg: "bg-gold/10",     border: "border-gold/30",    icon: ArrowUpRight },
  reversal_down:  { label: "REVERSAL ↓",    color: "text-gold",     bg: "bg-gold/10",     border: "border-gold/30",    icon: ArrowDownRight },
  neutral:        { label: "NEUTRAL",        color: "text-white/50", bg: "bg-white/5",     border: "border-white/10",   icon: Activity },
};

/* ─── State Flow Steps ─── */
const STATE_FLOW = [
  { key: "compression",  label: "Compression" },
  { key: "breakout",     label: "Breakout" },
  { key: "impulse",      label: "Impulse" },
  { key: "pullback",     label: "Pullback" },
  { key: "continuation", label: "Continuation" },
  { key: "weakening",    label: "Weakening" },
  { key: "range",        label: "Range" },
];

function getActiveFlowStep(ms: MarketState): string {
  if (ms.compression_ratio < 0.9 && ms.regime === "neutral") return "compression";
  if (ms.regime.startsWith("breakout")) return "breakout";
  if (ms.regime.startsWith("trend") && ms.efficiency_ratio > 0.6) return "impulse";
  if (ms.regime.startsWith("trend") && ms.efficiency_ratio <= 0.6) return "pullback";
  if (ms.regime.startsWith("trend") && ms.body_strength > 1.0) return "continuation";
  if (ms.recent_minor_high < ms.prior_minor_high && ms.ema_slope < 0) return "weakening";
  if (ms.regime === "range") return "range";
  if (ms.regime.startsWith("reversal")) return "weakening";
  return "compression";
}

/* ─── Swing Sequence ─── */
function getSwingSequence(ms: MarketState): string[] {
  const tags: string[] = [];
  // Higher Highs / Lower Highs
  if (ms.recent_minor_high > ms.prior_minor_high) tags.push("HH");
  else if (ms.recent_minor_high < ms.prior_minor_high) tags.push("LH");
  else tags.push("EH");
  // Higher Lows / Lower Lows
  if (ms.recent_minor_low > ms.prior_minor_low) tags.push("HL");
  else if (ms.recent_minor_low < ms.prior_minor_low) tags.push("LL");
  else tags.push("EL");
  return tags;
}

/* ─── Metric Color Helper ─── */
function metricTone(value: number, thresholds: [number, number], inverse = false): string {
  const [lo, hi] = thresholds;
  if (inverse) {
    if (value <= lo) return "text-bullish";
    if (value >= hi) return "text-bearish";
    return "text-warning";
  }
  if (value >= hi) return "text-bullish";
  if (value <= lo) return "text-bearish";
  return "text-warning";
}

/* ─── Main Component ─── */
export default function MarketStatePanel() {
  const marketState = useMidasStore((s) => s.marketState);

  if (!marketState) {
    return (
      <div className="bg-[#131722] rounded-lg border border-white/5 p-4 flex flex-col items-center justify-center text-center">
        <Gauge className="h-5 w-5 text-white/10 mb-2" />
        <p className="text-[10px] font-medium text-white/30 uppercase tracking-wider">
          Market State Engine
        </p>
        <p className="text-[9px] text-white/15 mt-1">Waiting for first analysis cycle…</p>
      </div>
    );
  }

  const ms = marketState;
  const regimeCfg = REGIME_DISPLAY[ms.regime] || REGIME_DISPLAY.neutral;
  const RegimeIcon = regimeCfg.icon;
  const activeStep = getActiveFlowStep(ms);
  const swingSeq = getSwingSequence(ms);
  const priceToResistance = ms.resistance - ms.current_price;
  const priceToSupport = ms.current_price - ms.support;

  return (
    <div className="bg-[#131722] rounded-lg border border-white/5 overflow-hidden">
      {/* ── Header: Market Regime Badge ── */}
      <div className={`px-3 py-2.5 ${regimeCfg.bg} border-b ${regimeCfg.border} flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <div className={`h-6 w-6 rounded-md ${regimeCfg.bg} border ${regimeCfg.border} flex items-center justify-center`}>
            <RegimeIcon className={`h-3.5 w-3.5 ${regimeCfg.color}`} />
          </div>
          <div>
            <span className={`text-[11px] font-bold tracking-wider ${regimeCfg.color}`}>
              {regimeCfg.label}
            </span>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-[8px] text-white/30 uppercase tracking-widest">
                {ms.timeframe} · {ms.source}
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

      <div className="p-3 space-y-3">
        {/* ── State Flow Indicator ── */}
        <div>
          <p className="text-[8px] font-bold text-white/25 uppercase tracking-widest mb-1.5">
            Market Phase
          </p>
          <div className="flex items-center gap-0.5">
            {STATE_FLOW.map((step, i) => {
              const isActive = step.key === activeStep;
              const isPast = STATE_FLOW.findIndex((s) => s.key === activeStep) > i;
              return (
                <div key={step.key} className="flex-1 flex flex-col items-center">
                  <div
                    className={`w-full h-1 rounded-full transition-all duration-500 ${
                      isActive
                        ? "bg-gold shadow-[0_0_6px_rgba(245,158,11,0.4)]"
                        : isPast
                        ? "bg-white/15"
                        : "bg-white/5"
                    }`}
                  />
                  <span
                    className={`text-[7px] mt-1 tracking-wide ${
                      isActive ? "text-gold font-bold" : "text-white/20"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Structure Metrics Grid ── */}
        <div>
          <p className="text-[8px] font-bold text-white/25 uppercase tracking-widest mb-1.5">
            Structure Metrics
          </p>
          <div className="grid grid-cols-3 gap-1.5">
            {[
              {
                label: "ATR",
                value: ms.atr.toFixed(2),
                icon: Activity,
                tone: "text-white/80",
              },
              {
                label: "Compression",
                value: ms.compression_ratio.toFixed(2) + "x",
                icon: Layers,
                tone: metricTone(ms.compression_ratio, [0.85, 1.15], true),
              },
              {
                label: "Efficiency",
                value: (ms.efficiency_ratio * 100).toFixed(0) + "%",
                icon: Gauge,
                tone: metricTone(ms.efficiency_ratio, [0.3, 0.55]),
              },
              {
                label: "Rel. Volume",
                value: ms.relative_volume.toFixed(2) + "x",
                icon: BarChart3,
                tone: metricTone(ms.relative_volume, [0.8, 1.25]),
              },
              {
                label: "Body Str.",
                value: ms.body_strength.toFixed(2) + "x",
                icon: Zap,
                tone: metricTone(ms.body_strength, [0.7, 1.1]),
              },
              {
                label: "EMA Slope",
                value: ms.ema_slope > 0 ? "+" + ms.ema_slope.toFixed(2) : ms.ema_slope.toFixed(2),
                icon: ms.ema_slope >= 0 ? TrendingUp : TrendingDown,
                tone: ms.ema_slope > 0 ? "text-bullish" : ms.ema_slope < 0 ? "text-bearish" : "text-white/50",
              },
            ].map(({ label, value, icon: Icon, tone }) => (
              <div
                key={label}
                className="rounded-md bg-black/30 border border-white/5 p-1.5 flex flex-col"
              >
                <div className="flex items-center gap-1 mb-0.5">
                  <Icon className="h-2.5 w-2.5 text-white/20" />
                  <span className="text-[7px] font-bold text-white/25 uppercase tracking-widest truncate">
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

        {/* ── Key Levels ── */}
        <div>
          <p className="text-[8px] font-bold text-white/25 uppercase tracking-widest mb-1.5">
            Key Levels
          </p>
          <div className="space-y-1">
            {[
              { label: "Resistance", price: ms.resistance, dist: priceToResistance, color: "text-bearish", barColor: "bg-bearish/40" },
              { label: "Support", price: ms.support, dist: priceToSupport, color: "text-bullish", barColor: "bg-bullish/40" },
            ].map(({ label, price, dist, color, barColor }) => {
              const pct = Math.min(Math.abs(dist) / Math.max(ms.range_width, 0.01), 1);
              return (
                <div key={label} className="rounded bg-black/20 border border-white/5 px-2 py-1.5">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5">
                      <Shield className={`h-2.5 w-2.5 ${color}`} />
                      <span className="text-[8px] font-bold text-white/30 uppercase tracking-widest">
                        {label}
                      </span>
                    </div>
                    <span className={`text-[10px] font-bold font-[family-name:var(--font-jetbrains-mono)] ${color}`}>
                      {formatPrice(price)}
                    </span>
                  </div>
                  <div className="h-1 w-full bg-white/5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-700 ${barColor}`}
                      style={{ width: `${(1 - pct) * 100}%` }}
                    />
                  </div>
                  <div className="flex justify-between mt-0.5">
                    <span className="text-[7px] text-white/20">
                      {Math.abs(dist).toFixed(2)} pts away
                    </span>
                    <span className="text-[7px] text-white/15">
                      {ms.regime === "range" ? `Touches: ${label === "Resistance" ? ms.boundary_touches_high : ms.boundary_touches_low}` : ""}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── Swing Structure ── */}
        <div className="flex items-center justify-between rounded bg-black/20 border border-white/5 px-2 py-1.5">
          <div className="flex items-center gap-1.5">
            <Activity className="h-2.5 w-2.5 text-white/20" />
            <span className="text-[8px] font-bold text-white/25 uppercase tracking-widest">
              Swing Structure
            </span>
          </div>
          <div className="flex items-center gap-1">
            {swingSeq.map((tag, i) => {
              const isBull = tag === "HH" || tag === "HL";
              const isBear = tag === "LH" || tag === "LL";
              return (
                <span
                  key={i}
                  className={`text-[9px] font-bold font-[family-name:var(--font-jetbrains-mono)] px-1 py-0.5 rounded ${
                    isBull
                      ? "bg-bullish/10 text-bullish border border-bullish/20"
                      : isBear
                      ? "bg-bearish/10 text-bearish border border-bearish/20"
                      : "bg-white/5 text-white/40 border border-white/10"
                  }`}
                >
                  {tag}
                </span>
              );
            })}
          </div>
        </div>

        {/* ── Notes / Tags ── */}
        {ms.notes.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {ms.notes.map((note, i) => (
              <span
                key={i}
                className="text-[8px] font-bold px-1.5 py-0.5 rounded-full bg-gold/10 text-gold/70 border border-gold/15 uppercase tracking-wider"
              >
                {note.replace("_", " ")}
              </span>
            ))}
          </div>
        )}

        {/* ── Close Location Bar ── */}
        <div className="rounded bg-black/20 border border-white/5 px-2 py-1.5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[8px] font-bold text-white/25 uppercase tracking-widest">
              Close Location
            </span>
            <span className="text-[9px] font-bold font-[family-name:var(--font-jetbrains-mono)] text-white/60">
              {(ms.close_location * 100).toFixed(0)}%
            </span>
          </div>
          <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden relative">
            <div
              className="absolute h-full rounded-full transition-all duration-500"
              style={{
                width: `${ms.close_location * 100}%`,
                background: `linear-gradient(90deg, hsl(0,70%,55%), hsl(45,80%,55%), hsl(120,60%,45%))`,
              }}
            />
          </div>
          <div className="flex justify-between mt-0.5">
            <span className="text-[7px] text-white/15">Low</span>
            <span className="text-[7px] text-white/15">High</span>
          </div>
        </div>
      </div>
    </div>
  );
}
