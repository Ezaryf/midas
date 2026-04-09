"use client";

import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Clock3,
  Layers,
  Shield,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import type { AnalysisBatch, CandidateInsight, MarketState } from "@/lib/types";
import { formatPrice } from "@/lib/utils";

interface EngineInsightPanelProps {
  batch: AnalysisBatch | null;
  marketState: MarketState | null;
  noSetupMessage: string;
}

function toneForDirection(direction: CandidateInsight["direction"]) {
  if (direction === "BUY") return "text-bullish";
  if (direction === "SELL") return "text-bearish";
  return "text-warning";
}

function formatScore(value?: number) {
  return value == null ? "--" : Math.round(value).toString();
}

function formatPercent(value?: number) {
  return value == null ? "--" : `${Math.round(value)}%`;
}

export default function EngineInsightPanel({
  batch,
  marketState,
  noSetupMessage,
}: EngineInsightPanelProps) {
  if (!batch?.engine_insight) {
    return (
      <div className="rounded-lg border border-white/5 bg-[#131722] p-4 text-center overflow-hidden relative">
        <div className="absolute inset-0 bg-gold/5 blur-3xl animate-pulse" />
        <Activity className="mx-auto h-5 w-5 text-gold animate-bounce relative z-10" />
        <p className="mt-3 text-[10px] font-bold uppercase tracking-widest text-white/40 relative z-10 flex items-center justify-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-gold animate-pulse" /> Engine Desk Validating
        </p>
        <p className="mt-1.5 text-[10px] leading-relaxed text-white/20 relative z-10">
          Actively calculating mathematical tick streams.
        </p>
        
        {marketState && (
          <div className="mt-4 pt-4 border-t border-white/5 grid grid-cols-2 gap-2 text-left relative z-10">
            <div className="rounded bg-black/20 p-2 border border-white/5">
              <p className="text-[8px] font-bold uppercase tracking-widest text-white/30">Volatility (ATR)</p>
              <p className="text-[10px] font-[family-name:var(--font-jetbrains-mono)] text-white/70 mt-1">{marketState.atr.toFixed(2)}</p>
            </div>
            <div className="rounded bg-black/20 p-2 border border-white/5">
              <p className="text-[8px] font-bold uppercase tracking-widest text-white/30">Efficiency</p>
              <p className="text-[10px] font-[family-name:var(--font-jetbrains-mono)] text-white/70 mt-1">{(marketState.efficiency_ratio * 100).toFixed(0)}%</p>
            </div>
            <div className="rounded bg-black/20 p-2 border border-white/5 col-span-2">
              <p className="flex justify-between items-center text-[8px] font-bold uppercase tracking-widest text-white/30">
                <span>Compression</span>
                <span className="text-white/40">{marketState.compression_ratio.toFixed(2)}x</span>
              </p>
              <div className="mt-1.5 w-full h-1 bg-white/5 rounded-full overflow-hidden">
                 <div className="h-full bg-gold/50 rounded-full transition-all duration-300" style={{ width: `${Math.min(100, Math.max(5, marketState.compression_ratio * 50))}%` }} />
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  const insight = batch.engine_insight;
  const context = batch.context_summary;
  const rejected = insight.candidates.filter((candidate) => candidate.status === "rejected");
  const rejectedLong = rejected.find((candidate) => candidate.direction === "BUY");
  const rejectedShort = rejected.find((candidate) => candidate.direction === "SELL");
  const confidenceCap = context?.datasets?.reduce((max, dataset) => {
    return Math.max(max, dataset.source_quality.confidence_cap);
  }, 0) ?? 0;
  const timeframeStack = context?.datasets?.map((dataset) => dataset.timeframe.toUpperCase()).join(" / ") ?? "--";
  const metrics = marketState ? [
    { label: "ATR", value: marketState.atr.toFixed(2), tone: "text-white" },
    { label: "Compression", value: `${marketState.compression_ratio.toFixed(2)}x`, tone: marketState.compression_ratio < 0.9 ? "text-gold" : "text-white/70" },
    { label: "Efficiency", value: `${Math.round(marketState.efficiency_ratio * 100)}%`, tone: marketState.efficiency_ratio > 0.55 ? "text-bullish" : marketState.efficiency_ratio < 0.3 ? "text-bearish" : "text-warning" },
    { label: "Rel Vol", value: `${marketState.relative_volume.toFixed(2)}x`, tone: marketState.relative_volume > 1.2 ? "text-gold" : "text-white/70" },
  ] : [];

  const topPatterns = insight.patterns.slice(0, 6);

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-white/5 bg-[#131722] p-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[9px] font-bold uppercase tracking-widest text-white/30">Desk Summary</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <span className="rounded border border-gold/20 bg-gold/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-gold">
                {insight.phase.label}
              </span>
              <span className="rounded border border-white/10 bg-black/20 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-white/45">
                {batch.market_regime.replaceAll("_", " ")}
              </span>
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-white/45">
              {insight.summary}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">Last Analysis</p>
            <p className="mt-1 text-[10px] font-[family-name:var(--font-jetbrains-mono)] text-white/70">
              {new Date(batch.evaluated_at).toLocaleTimeString()}
            </p>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-md border border-white/5 bg-black/20 p-2">
            <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">Timeframes</p>
            <p className="mt-1 text-[10px] font-[family-name:var(--font-jetbrains-mono)] text-white/70">
              {timeframeStack}
            </p>
          </div>
          <div className="rounded-md border border-white/5 bg-black/20 p-2">
            <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">Confidence Cap</p>
            <p className={`mt-1 text-[10px] font-[family-name:var(--font-jetbrains-mono)] ${confidenceCap >= 95 ? "text-bullish" : "text-warning"}`}>
              {confidenceCap > 0 ? `${Math.round(confidenceCap)}%` : "--"}
            </p>
          </div>
        </div>

        {metrics.length > 0 && (
          <div className="mt-3">
            <div className="mb-2 flex items-center gap-1.5">
              <BarChart3 className="h-3 w-3 text-white/30" />
              <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">Calculation Metrics</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {metrics.map((metric) => (
                <div key={metric.label} className="rounded-md border border-white/5 bg-black/20 p-2">
                  <p className="text-[8px] font-bold uppercase tracking-widest text-white/20">{metric.label}</p>
                  <p className={`mt-1 text-[10px] font-[family-name:var(--font-jetbrains-mono)] ${metric.tone}`}>
                    {metric.value}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-white/5 bg-[#131722] p-3">
        <div className="mb-2 flex items-center gap-1.5">
          <Shield className="h-3 w-3 text-white/30" />
          <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">Decision Gates</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {insight.decision_gates.map((gate) => (
            <div
              key={gate.code}
              className={`rounded-md border px-2 py-1 ${
                gate.passed
                  ? "border-bullish/20 bg-bullish/10"
                  : gate.blocking
                  ? "border-bearish/20 bg-bearish/10"
                  : "border-warning/20 bg-warning/10"
              }`}
              title={gate.detail}
            >
              <p className={`text-[9px] font-bold uppercase tracking-widest ${
                gate.passed ? "text-bullish" : gate.blocking ? "text-bearish" : "text-warning"
              }`}>
                {gate.label}
              </p>
              <p className="mt-0.5 text-[9px] leading-relaxed text-white/35">{gate.detail}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-lg border border-white/5 bg-[#131722] p-3">
        <div className="mb-2 flex items-center gap-1.5">
          <Layers className="h-3 w-3 text-white/30" />
          <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">Pattern Tape</p>
        </div>
        {topPatterns.length === 0 ? (
          <p className="text-[10px] text-white/30">No supporting chart or candlestick pattern met the confidence filter this cycle.</p>
        ) : (
          <div className="space-y-2">
            {topPatterns.map((pattern, index) => (
              <div key={`${pattern.type}-${pattern.timeframe}-${index}`} className="rounded-md border border-white/5 bg-black/20 p-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className={`text-[10px] font-bold ${pattern.direction === "BUY" ? "text-bullish" : "text-bearish"}`}>
                        {pattern.direction === "BUY" ? <ArrowUpRight className="inline h-3 w-3" /> : <ArrowDownRight className="inline h-3 w-3" />} {pattern.type}
                      </span>
                      <span className="rounded bg-white/5 px-1.5 py-0.5 text-[8px] uppercase tracking-widest text-white/30">
                        {pattern.family}
                      </span>
                      <span className="rounded bg-white/5 px-1.5 py-0.5 text-[8px] uppercase tracking-widest text-white/30">
                        {pattern.timeframe}
                      </span>
                      <span className={`rounded px-1.5 py-0.5 text-[8px] uppercase tracking-widest ${
                        pattern.relation === "support"
                          ? "bg-bullish/10 text-bullish"
                          : pattern.relation === "conflict"
                          ? "bg-bearish/10 text-bearish"
                          : "bg-white/5 text-white/40"
                      }`}>
                        {pattern.relation}
                      </span>
                    </div>
                    <p className="mt-1 text-[9px] leading-relaxed text-white/35">{pattern.description}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] font-[family-name:var(--font-jetbrains-mono)] text-gold">
                      {Math.round(pattern.confidence)}%
                    </p>
                    {pattern.entry_price != null && (
                      <p className="mt-0.5 text-[9px] text-white/25">{formatPrice(pattern.entry_price)}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-white/5 bg-[#131722] p-3">
        <div className="mb-2 flex items-center gap-1.5">
          <Zap className="h-3 w-3 text-white/30" />
          <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">Setup Ladder</p>
        </div>

        <div className="space-y-2">
          {insight.candidates.slice(0, 6).map((candidate, index) => (
            <div key={`${candidate.status}-${candidate.setup_type}-${candidate.entry_price}-${index}`} className="rounded-md border border-white/5 bg-black/20 p-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className={`text-[10px] font-bold ${toneForDirection(candidate.direction)}`}>
                      {candidate.direction}
                    </span>
                    <span className="text-[9px] uppercase tracking-widest text-white/30">
                      {candidate.setup_type.replaceAll("_", " ")}
                    </span>
                    <span className={`rounded px-1.5 py-0.5 text-[8px] uppercase tracking-widest ${
                      candidate.status === "selected"
                        ? "bg-gold/10 text-gold"
                        : candidate.status === "backup"
                        ? "bg-white/5 text-white/45"
                        : "bg-bearish/10 text-bearish"
                    }`}>
                      {candidate.status}
                    </span>
                  </div>
                  <p className="mt-1 text-[9px] leading-relaxed text-white/35">
                    Entry {formatPrice(candidate.entry_price)} · SL {formatPrice(candidate.stop_loss)} · TP1 {formatPrice(candidate.take_profit_1)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] font-[family-name:var(--font-jetbrains-mono)] text-gold">
                    {formatScore(candidate.score)}
                  </p>
                  <p className="text-[8px] uppercase tracking-widest text-white/20">score</p>
                </div>
              </div>

              <div className="mt-2 grid grid-cols-4 gap-1.5">
                {[
                  { label: "RR", value: candidate.rr > 0 ? `${candidate.rr.toFixed(2)}x` : "--" },
                  { label: "Act", value: formatPercent(candidate.evidence.actionability) },
                  { label: "Conf", value: formatPercent(candidate.evidence.confluence) },
                  { label: "Penalty", value: candidate.evidence.conflict_penalty ? `${candidate.evidence.conflict_penalty.toFixed(0)}` : "0" },
                ].map((metric) => (
                  <div key={metric.label} className="rounded bg-white/5 p-1.5">
                    <p className="text-[8px] uppercase tracking-widest text-white/20">{metric.label}</p>
                    <p className="mt-0.5 text-[9px] font-[family-name:var(--font-jetbrains-mono)] text-white/65">{metric.value}</p>
                  </div>
                ))}
              </div>

              {candidate.blocker_reasons.length > 0 && (
                <div className="mt-2 rounded border border-white/5 bg-black/30 p-2">
                  {candidate.blocker_reasons.slice(0, 2).map((reason, reasonIndex) => (
                    <p key={`${reason.code}-${reasonIndex}`} className="text-[9px] leading-relaxed text-white/35">
                      {reason.blocking ? "Blocker:" : "Context:"} {reason.message}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {batch.primary.direction === "HOLD" && (
        <div className="rounded-lg border border-warning/20 bg-warning/5 p-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 text-warning" />
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-warning">No Trade Diagnosis</p>
              <p className="mt-1 text-[10px] leading-relaxed text-white/35">{noSetupMessage}</p>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2">
            {[rejectedLong, rejectedShort].filter(Boolean).map((candidate) => (
              <div key={`${candidate!.direction}-${candidate!.setup_type}`} className="rounded-md border border-white/5 bg-black/20 p-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    {candidate!.direction === "BUY" ? (
                      <TrendingUp className="h-3 w-3 text-bullish" />
                    ) : (
                      <TrendingDown className="h-3 w-3 text-bearish" />
                    )}
                    <span className={`text-[10px] font-bold ${toneForDirection(candidate!.direction)}`}>
                      Rejected {candidate!.direction}
                    </span>
                  </div>
                  <span className="text-[10px] font-[family-name:var(--font-jetbrains-mono)] text-gold">
                    {formatScore(candidate!.score)}
                  </span>
                </div>
                <p className="mt-1 text-[9px] uppercase tracking-widest text-white/30">
                  {candidate!.setup_type.replaceAll("_", " ")}
                </p>
                <p className="mt-1 text-[9px] leading-relaxed text-white/35">
                  {candidate!.blocker_reasons[0]?.message ?? candidate!.reasoning}
                </p>
              </div>
            ))}
            {!rejectedLong && !rejectedShort && (
              <div className="rounded-md border border-white/5 bg-black/20 p-2">
                <div className="flex items-center gap-1.5">
                  <Clock3 className="h-3 w-3 text-white/30" />
                  <p className="text-[9px] leading-relaxed text-white/35">
                    No directional candidate passed the engine’s ranking filters this cycle.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
