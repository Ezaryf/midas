"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSocket } from "@/hooks/useSocket";
import { useMidasStore } from "@/store/useMidasStore";
import { useLiveCandles, type Timeframe } from "@/hooks/useLiveCandles";
import { useCalendar } from "@/hooks/useCalendar";
import { useNews } from "@/hooks/useNews";
import { useConfig } from "@/hooks/useConfig";
import { useSignalHistory } from "@/hooks/useSignalHistory";
import { usePerformance } from "@/hooks/usePerformance";
import { useSignalTracker } from "@/hooks/useSignalTracker";
import { useLivePrice } from "@/hooks/useLivePrice";
import type { PerformanceStats } from "@/hooks/usePerformance";
import {
  TrendingUp, Settings, Newspaper, CalendarDays, History,
  BarChart3, Trophy, Target, Percent, Trash2, ChevronLeft, ChevronRight, Loader2, Terminal, Activity
} from "lucide-react";
import { formatPrice } from "@/lib/utils";
import { LineStyle } from "lightweight-charts";
import SignalCard from "@/components/signals/SignalCard";
import SignalHistory from "@/components/signals/SignalHistory";
import NewsSentiment from "@/components/data/NewsSentiment";
import EconomicCalendar from "@/components/data/EconomicCalendar";

import EngineInsightPanel from "@/components/signals/EngineInsightPanel";
import MarketStatePanel from "@/components/signals/MarketStatePanel";

const TradingViewChart = dynamic(
  () => import("@/components/chart/TradingViewChart"),
  { ssr: false, loading: () => <div className="w-full h-full bg-transparent" /> }
);

type RightTab = "engine" | "news" | "calendar" | "history";
type BottomTab = "terminal" | "market-state" | "performance";

type TradingStyle = "Scalper" | "Intraday" | "Swing";

type AnalysisEngineCardProps = {
  tradingStyle: TradingStyle;
  isConnected: boolean;
  nextAnalysis: number;
  lastAnalysis: Date | null;
  targetSymbol: string;
  price: number;
  livePrice: { bid: number; ask: number } | null;
  spread: number;
  lastTickLabel: string;
  livePriceError: string | null;
  liveStatusLabel: string;
  isSymbolMatch: boolean;
  isStale: boolean;
  configApiKey?: string;
  latestRegimeSummary?: string | null;
};

function AnalysisEngineCard({
  tradingStyle,
  isConnected,
  nextAnalysis,
  lastAnalysis,
  targetSymbol,
  price,
  livePrice,
  spread,
  lastTickLabel,
  livePriceError,
  liveStatusLabel,
  isSymbolMatch,
  isStale,
  configApiKey,
  latestRegimeSummary,
}: AnalysisEngineCardProps) {
  return (
    <div className="bg-[#131722] rounded-lg border border-white/5 p-3">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-[9px] font-bold text-white/40 uppercase tracking-widest">Analysis Engine</h2>
        <span className="text-[9px] font-bold text-gold bg-gold/10 px-1.5 py-0.5 rounded border border-gold/20 uppercase tracking-wider">{tradingStyle}</span>
      </div>
      <div className="flex items-center justify-between bg-black/20 p-2 rounded">
        {isConnected ? (
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse shadow-[0_0_5px_rgba(34,197,94,0.8)]" />
            <span className="text-[10px] font-medium text-bullish tracking-wide uppercase">Active</span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <div className="h-1.5 w-1.5 rounded-full bg-bearish" />
            <span className="text-[10px] font-medium text-bearish tracking-wide uppercase">Paused / Offline</span>
          </div>
        )}
        {isConnected && (
          <div className="text-[9px] font-(family-name:--font-jetbrains-mono) text-white/40">
            Next TCK in <span className="text-white font-bold">{nextAnalysis}s</span>
          </div>
        )}
      </div>
      {lastAnalysis && (
        <div className="mt-2 text-[9px] font-(family-name:--font-jetbrains-mono) text-white/30 text-right">
          Last execution: {lastAnalysis.toLocaleTimeString()}
        </div>
      )}
      <div className="mt-3 rounded-md border border-white/5 bg-black/20 p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className={`h-3.5 w-3.5 ${!isConnected ? "text-bearish" : !isSymbolMatch || isStale ? "text-warning" : "text-bullish"}`} />
            <p className="text-[9px] font-bold uppercase tracking-widest text-white/35">{targetSymbol} Live Price</p>
          </div>
          <span className="text-[9px] font-(family-name:--font-jetbrains-mono) text-white/30">{lastTickLabel}</span>
        </div>
        <div className="mt-2 grid grid-cols-3 gap-2">
          {[
            { label: "Bid", value: price > 0 ? formatPrice(livePrice?.bid ?? 0) : "--.--", tone: "text-white" },
            { label: "Ask", value: price > 0 ? formatPrice(livePrice?.ask ?? 0) : "--.--", tone: "text-white/80" },
            { label: "Spread", value: price > 0 ? spread.toFixed(2) : "--", tone: spread <= 0.5 ? "text-bullish" : spread <= 1 ? "text-warning" : "text-bearish" },
          ].map((item) => (
            <div key={item.label} className="rounded bg-white/5 p-2">
              <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">{item.label}</p>
              <p className={`mt-1 text-xs font-bold font-(family-name:--font-jetbrains-mono) ${item.tone}`}>{item.value}</p>
            </div>
          ))}
        </div>
        <p className={`mt-2 text-[10px] leading-relaxed ${!isConnected ? "text-bearish/80" : !isSymbolMatch || isStale ? "text-warning/80" : "text-white/45"}`}>
          {livePriceError || liveStatusLabel}
        </p>
      </div>
      {!configApiKey && <p className="text-[10px] font-semibold text-warning mt-2 bg-warning/10 p-2 rounded border border-warning/20">No API key found. System requires LLM key in <Link href="/config" className="underline hover:text-white">Settings</Link>.</p>}
      {latestRegimeSummary && (
        <p className="mt-2 text-[10px] leading-relaxed text-white/35">
          {latestRegimeSummary}
        </p>
      )}
    </div>
  );
}

type PerformancePanelProps = {
  perf: PerformanceStats;
  resetting: boolean;
  resetPerformance: () => Promise<void>;
};

function PerformancePanel({ perf, resetting, resetPerformance }: PerformancePanelProps) {
  return (
    <div className="bg-[#131722] rounded-lg border border-white/5 p-3">
      <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2">
        <p className="text-[9px] font-bold text-white/30 uppercase tracking-widest">Metrics / Performance</p>
        <button
          onClick={resetPerformance}
          disabled={resetting}
          className="flex items-center gap-1 rounded bg-black/20 px-1.5 py-1 text-[9px] font-bold text-white/20 hover:text-bearish hover:bg-bearish/10 border border-transparent hover:border-bearish/20 transition-all disabled:opacity-40 uppercase tracking-wider"
          title="Reset all performance stats"
        >
          {resetting ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Trash2 className="h-2.5 w-2.5" />}
          {resetting ? "Resetting..." : "Reset"}
        </button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {[
          { label: "Win Rate", value: perf.winRate + "%", color: "text-bullish" },
          { label: "P.Factor", value: perf.profitFactor > 0 ? perf.profitFactor + "x" : "-", color: "text-gold" },
          { label: "Today PnL", value: (perf.todayPnl >= 0 ? "+" : "") + "$" + perf.todayPnl.toFixed(0), color: perf.todayPnl >= 0 ? "text-bullish" : "text-bearish" },
          { label: "Week PnL", value: (perf.weekPnl >= 0 ? "+" : "") + "$" + perf.weekPnl.toFixed(0), color: perf.weekPnl >= 0 ? "text-bullish" : "text-bearish" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-white/5 p-3 rounded flex flex-col justify-between min-h-20">
            <p className="text-[9px] font-bold uppercase tracking-widest text-white/30 mb-1">{label}</p>
            <p className={`text-sm font-bold font-(family-name:--font-jetbrains-mono) ${color}`}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  // Persist timeframe & tradingStyle in localStorage so they survive navigation
  const [timeframe, setTimeframeRaw] = useState<Timeframe>("H2");
  const [tradingStyle, setTradingStyleRaw] = useState<TradingStyle>("Scalper");
  const [styleChanging, setStyleChanging] = useState(false);
  const [rightTab, setRightTab]       = useState<RightTab>("engine");
  const [bottomTab, setBottomTab]     = useState<BottomTab>("terminal");
  const [bottomPanelHeight, setBottomPanelHeightRaw] = useState(288);
  const [isResizing, setIsResizing] = useState(false);
  const [rightOpen, setRightOpen]     = useState(true);
  const [leftOpen, setLeftOpen]       = useState(true);
  const [lastAnalysis, setLastAnalysis] = useState<Date | null>(null);
  const [nextAnalysis, setNextAnalysis] = useState<number>(10);

  useEffect(() => {
    Promise.resolve().then(() => {
      try {
        const savedTf = localStorage.getItem("midas_timeframe") as Timeframe | null;
        if (savedTf && ["M1","M3","M5","M15","H1","H4"].includes(savedTf)) setTimeframeRaw(savedTf);
        
        const savedTs = localStorage.getItem("midas_trading_style") as TradingStyle | null;
        if (savedTs && ["Scalper","Intraday","Swing"].includes(savedTs)) setTradingStyleRaw(savedTs);

        const savedHeight = localStorage.getItem("midas_bottom_panel_height");
        if (savedHeight) setBottomPanelHeightRaw(Number(savedHeight));
      } catch {}
    });
  }, []);

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault();
    setIsResizing(true);
    document.body.style.cursor = 'row-resize';
  }, []);

  useEffect(() => {
    if (!isResizing) return;
    
    const handleMove = (e: PointerEvent) => {
      // Don't resize if we accidentally select text or leave the window
      const newHeight = window.innerHeight - e.clientY;
      const clamped = Math.max(160, Math.min(newHeight, window.innerHeight * 0.8));
      setBottomPanelHeightRaw(clamped);
    };
    
    const handleUp = (e: PointerEvent) => {
      setIsResizing(false);
      globalThis.document.body.style.cursor = '';
      const newHeight = globalThis.window.innerHeight - e.clientY;
      const clamped = Math.max(160, Math.min(newHeight, globalThis.window.innerHeight * 0.8));
      try { localStorage.setItem("midas_bottom_panel_height", String(clamped)); } catch { /* ignore */ }
    };
    
    globalThis.addEventListener('pointermove', handleMove);
    globalThis.addEventListener('pointerup', handleUp);
    return () => {
      globalThis.removeEventListener('pointermove', handleMove);
      globalThis.removeEventListener('pointerup', handleUp);
    };
  }, [isResizing]);

  // Wrapped setters that also persist
  const setTimeframe = useCallback((tf: Timeframe) => {
    setTimeframeRaw(tf);
    try { localStorage.setItem("midas_timeframe", tf); } catch { /* ignore */ }
  }, []);



  const setTradingStyle = useCallback((style: TradingStyle) => {
    setTradingStyleRaw(style);
    try { localStorage.setItem("midas_trading_style", style); } catch { /* ignore */ }
  }, []);

  useSocket();
  useSignalTracker();
  const { activeSignal, latestBatch, marketState, signalHistory, isConnected, clearActiveSignal, targetSymbol, setTargetSymbol } = useMidasStore();
  
  // Track when signals arrive (automatic analysis indicator)
  useEffect(() => {
    if (activeSignal) {
      // Use a microtask to avoid cascading renders
      Promise.resolve().then(() => setLastAnalysis(new Date()));
    }
  }, [activeSignal]);

  // Sync targetSymbol with backend
  useEffect(() => {
    if (!targetSymbol) return;
    fetch("/api/target-symbol", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_symbol: targetSymbol }),
      signal: AbortSignal.timeout(5_000),
    }).catch(() => {});
  }, [targetSymbol]);
  const { config } = useConfig();
  const { stats: perf, resetting, resetPerformance } = usePerformance();
  const {
    data: livePrice,
    error: livePriceError,
    isStale,
    ageMs,
    isSymbolMatch,
    currentSymbol,
    activeSymbol,
  } = useLivePrice();
  
  // Countdown timer for next analysis
  useEffect(() => {
    const interval = setInterval(() => {
      setNextAnalysis(prev => {
        if (prev <= 1) return 10; // Reset to 10 seconds
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleStyleChange = useCallback(async (style: TradingStyle) => {
    if (style === tradingStyle) return;
    setStyleChanging(true);
    setTradingStyle(style);
    clearActiveSignal();
    // Clear history that doesn't match the new style
    useMidasStore.setState((s) => ({
      latestBatch: null,
      activeSignal: null,
      signalHistory: s.signalHistory.filter(
        sig => sig.trading_style?.toLowerCase() === style.toLowerCase()
      ),
    }));

    // 1. Tell backend to switch its runtime trading style
    // 2. Then trigger a force-generate for the new style
    try {
      const cfg = localStorage.getItem("midas_config");
      const parsed = cfg ? JSON.parse(cfg) : {};

      // Set the backend loop's trading style
      await fetch("/api/trading-style", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trading_style: style }),
        signal: AbortSignal.timeout(5_000),
      }).catch(() => {});

      // Force-generate a signal with the new style
      await fetch("/api/signals/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trading_style: style,
          api_key: parsed.apiKey || undefined,
          ai_provider: parsed.aiProvider || "groq",
        }),
        signal: AbortSignal.timeout(30_000),
      });
    } catch {
      // Backend may not be reachable — signals will come from next loop cycle
    }
    setStyleChanging(false);
  }, [tradingStyle, clearActiveSignal, setTradingStyle]);

  const { candles: candleData, loading: candlesLoading } = useLiveCandles(timeframe);
  const { events: calendarEvents, loading: calendarLoading } = useCalendar();
  const { items: newsItems, loading: newsLoading } = useNews();
  const { signals: dbHistory, loading: historyLoading, clearing, clearHistory } = useSignalHistory();

  const displayHistory = useMemo(() => {
    // Prioritize local WebSocket signals first, fall back to DB history
    const base = signalHistory.length > 0 ? signalHistory : dbHistory;
    return base;
  }, [dbHistory, signalHistory]);

  const displaySignal = useMemo(() => {
    // STRICT: Only show signals that match the selected trading style
    if (activeSignal?.trading_style?.toLowerCase() === tradingStyle.toLowerCase()) return activeSignal;
    // Search history for a style-matched signal
    const styleMatch = [...displayHistory]
      .filter(s => s.trading_style?.toLowerCase() === tradingStyle.toLowerCase() && s.status !== "STOPPED" && s.status !== "HIT_TP1" && s.status !== "HIT_TP2")
      .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))[0];
    // NEVER fall back to a mismatched signal — return null instead
    return styleMatch ?? null;
  }, [activeSignal, displayHistory, tradingStyle]);

  const displayBackups = useMemo(() => {
    if (
      latestBatch &&
      latestBatch.symbol.toUpperCase() === targetSymbol.toUpperCase() &&
      latestBatch.trading_style.toLowerCase() === tradingStyle.toLowerCase()
    ) {
      return latestBatch.backups ?? [];
    }

    if (!displaySignal?.analysis_batch_id) return [];
    return displayHistory.filter((signal) =>
      signal.analysis_batch_id === displaySignal.analysis_batch_id &&
      !signal.is_primary &&
      signal.trading_style?.toLowerCase() === tradingStyle.toLowerCase() &&
      (signal.symbol || targetSymbol).toUpperCase() === targetSymbol.toUpperCase()
    ).slice(0, 2);
  }, [latestBatch, targetSymbol, tradingStyle, displaySignal, displayHistory]);

  // No manual generation needed - system is fully automatic via WebSocket

  const latestMatchingBatch = useMemo(() => {
    if (!latestBatch || !targetSymbol) return null;
    const batchSym = latestBatch.symbol.toUpperCase().replace(/\./g, '').replace('M', '');
    const target = targetSymbol.toUpperCase().replace(/\./g, '').replace('M', '');
    const isLocalSymbolMatch = batchSym === target ||
      (batchSym.includes('GOLD') && target.includes('XAU')) ||
      (batchSym.includes('XAU') && target.includes('GOLD'));

    if (
      isLocalSymbolMatch &&
      latestBatch.trading_style.toLowerCase() === tradingStyle.toLowerCase()
    ) {
      return latestBatch;
    }
    return null;
  }, [latestBatch, targetSymbol, tradingStyle]);

  const chartLines = useMemo(() => {
    const lines: Array<{ price: number; color: string; label: string; style: LineStyle }> = [];
    const MAX_CHART_SIGNALS = 8;
    const MAX_CANDIDATE_SETUPS = 4;
    // Dynamic color generator — HSL rotation for unlimited distinct colors
    const generateColor = (idx: number) => ({
      entry: `hsl(${(idx * 47) % 360}, 70%, 65%)`,
      sl:    `hsl(${(idx * 47 + 15) % 360}, 80%, 55%)`,
      tp:    `hsl(${(idx * 47 + 120) % 360}, 70%, 60%)`,
    });
    const isUsableLevel = (value: number | undefined) => typeof value === "number" && value > 0 && Number.isFinite(value);

    const candidatePool = (latestMatchingBatch?.engine_insight?.candidates ?? [])
      .filter((candidate) =>
        candidate.direction !== "HOLD" &&
        isUsableLevel(candidate.entry_price) &&
        isUsableLevel(candidate.stop_loss) &&
        isUsableLevel(candidate.take_profit_1)
      )
      .sort((a, b) => {
        const statusRank = { selected: 0, backup: 1, rejected: 2 } as const;
        const rankDelta = statusRank[a.status] - statusRank[b.status];
        if (rankDelta !== 0) return rankDelta;
        return (b.score ?? 0) - (a.score ?? 0);
      })
      .slice(0, MAX_CANDIDATE_SETUPS);

    if (candidatePool.length > 0) {
      candidatePool.forEach((candidate, idx) => {
        const c = generateColor(idx);
        let prefix = `R${idx + 1}`;
        if (candidate.status === "selected") {
          prefix = `A${idx + 1}`;
        } else if (candidate.status === "backup") {
          prefix = `B${idx + 1}`;
        }
        const directionCode = candidate.direction === "BUY" ? "L" : "S";
        const entryStyle = candidate.status === "rejected" ? LineStyle.Dashed : LineStyle.Solid;
        const riskStyle = candidate.status === "selected" ? LineStyle.Dashed : LineStyle.Dotted;

        lines.push(
          { price: candidate.entry_price, color: c.entry, label: `${prefix}${directionCode}-E`, style: entryStyle },
          { price: candidate.stop_loss, color: c.sl, label: `${prefix}${directionCode}-SL`, style: riskStyle },
          { price: candidate.take_profit_1, color: c.tp, label: `${prefix}${directionCode}-TP1`, style: LineStyle.Dashed },
        );

        if (isUsableLevel(candidate.take_profit_2)) {
          lines.push({
            price: candidate.take_profit_2,
            color: c.tp,
            label: `${prefix}${directionCode}-TP2`,
            style: LineStyle.Dotted,
          });
        }
      });

      return lines;
    }

    const active = displayHistory.filter(s =>
      s.status !== "STOPPED" && s.status !== "HIT_TP1" && s.status !== "HIT_TP2" &&
      s.entry_price && s.stop_loss && s.take_profit_1 && s.take_profit_2
    );
    // STRICT: only show lines for signals matching the current trading style AND target symbol
    const pool = active.filter(s => 
      s.trading_style?.toLowerCase() === tradingStyle.toLowerCase() && 
      (s.symbol || "XAUUSD").toUpperCase() === targetSymbol.toUpperCase()
    );

    // Deduplicate: one signal per price zone (5-point buckets for gold)
    const seen = new Set<number>();
    const unique = pool.filter(s => {
      const key = Math.round(s.entry_price / 5);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    // Sort by proximity to current price — closest entry = #1 (most actionable)
    // Break ties by confidence
    const currentPx = livePrice?.price ?? 0;
    const topN = [...unique]
      .sort((a, b) => {
        if (currentPx > 0) {
          const distA = Math.abs(a.entry_price - currentPx);
          const distB = Math.abs(b.entry_price - currentPx);
          if (Math.abs(distA - distB) > 1) return distA - distB; // closest first
        }
        return (b.confidence ?? 0) - (a.confidence ?? 0); // tie-break by confidence
      })
      .slice(0, MAX_CHART_SIGNALS);

    topN.forEach((sig, idx) => {
      const c = generateColor(idx);
      // Short labels — axis already shows the price number
      const n = topN.length > 1 ? `${idx + 1}` : "";
      lines.push(
        { price: sig.entry_price,   color: c.entry, label: `E${n}`,   style: LineStyle.Solid  },
        { price: sig.stop_loss,     color: c.sl,    label: `SL${n}`,  style: LineStyle.Dashed },
        { price: sig.take_profit_1, color: c.tp,    label: `TP1${n}`, style: LineStyle.Dashed },
        { price: sig.take_profit_2, color: c.tp,    label: `TP2${n}`, style: LineStyle.Dotted },
      );
    });

    return lines;
  }, [displayHistory, latestMatchingBatch, tradingStyle, livePrice?.price, targetSymbol]);

  const chartLegendItems = useMemo(() => {
    const liveCandidates = (latestMatchingBatch?.engine_insight?.candidates ?? [])
      .filter((candidate) => candidate.direction !== "HOLD" && candidate.entry_price > 0)
      .sort((a, b) => {
        const statusRank = { selected: 0, backup: 1, rejected: 2 } as const;
        const rankDelta = statusRank[a.status] - statusRank[b.status];
        if (rankDelta !== 0) return rankDelta;
        return (b.score ?? 0) - (a.score ?? 0);
      })
      .slice(0, 4)
      .map((candidate, index) => ({
        id: `${candidate.status}-${candidate.direction}-${candidate.entry_price}-${index}`,
        title: `${candidate.direction} ${candidate.setup_type.replaceAll("_", " ")}`,
        subtitle: `Entry ${formatPrice(candidate.entry_price)} | SL ${formatPrice(candidate.stop_loss)} | TP1 ${formatPrice(candidate.take_profit_1)}`,
        tone: candidate.status,
      }));

    if (liveCandidates.length > 0) return liveCandidates;

    return displayHistory
      .filter((signal) =>
        signal.status !== "STOPPED" &&
        signal.status !== "HIT_TP1" &&
        signal.status !== "HIT_TP2" &&
        signal.entry_price > 0 &&
        signal.trading_style?.toLowerCase() === tradingStyle.toLowerCase() &&
        (signal.symbol || "XAUUSD").toUpperCase() === targetSymbol.toUpperCase()
      )
      .slice(0, 2)
      .map((signal, index) => ({
        id: `${signal.id || signal.signal_id || signal.entry_price}-${index}`,
        title: `${signal.direction} live signal`,
        subtitle: `Entry ${formatPrice(signal.entry_price)} | SL ${formatPrice(signal.stop_loss)} | TP1 ${formatPrice(signal.take_profit_1)}`,
        tone: "history" as const,
      }));
  }, [displayHistory, latestMatchingBatch, targetSymbol, tradingStyle]);

  const handleExecuteSignal = useCallback(async () => {
    if (!displaySignal || displaySignal.direction === "HOLD") return { status: "error", message: "No actionable signal" };
    try {
      const res = await fetch("/api/signals/execute", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          direction: displaySignal.direction, entry_price: displaySignal.entry_price,
          stop_loss: displaySignal.stop_loss, take_profit_1: displaySignal.take_profit_1,
          take_profit_2: displaySignal.take_profit_2, confidence: displaySignal.confidence,
          reasoning: displaySignal.reasoning, trading_style: displaySignal.trading_style,
        }),
        signal: AbortSignal.timeout(10_000),
      });
      return await res.json();
    } catch { return { status: "error", message: "Backend unreachable" }; }
  }, [displaySignal]);

  const price = livePrice?.price ?? 0;
  const change = livePrice?.change ?? 0;
  const changePct = livePrice?.changePercent ?? 0;
  const spread = livePrice?.spread ?? 0;
  const lastTickLabel = useMemo(() => {
    if (ageMs == null) return "No tick yet";
    if (ageMs < 1000) return "Updated just now";
    if (ageMs < 60_000) return `Updated ${Math.floor(ageMs / 1000)}s ago`;
    return `Updated ${Math.floor(ageMs / 60_000)}m ago`;
  }, [ageMs]);
  const liveStatusLabel = useMemo(() => {
    if (!isConnected) return "MT5 offline";
    if (!isSymbolMatch) return `Symbol mismatch: MT5 ${currentSymbol}, dashboard ${activeSymbol}`;
    if (isStale) return "Live feed stale";
    if (price > 0) return "Live ticks streaming";
    return "Waiting for live tick";
  }, [isConnected, isSymbolMatch, currentSymbol, activeSymbol, isStale, price]);
  const noTradeReasons = useMemo(() => {
    return latestMatchingBatch?.primary?.no_trade_reasons ?? [];
  }, [latestMatchingBatch]);
  const noSetupMessage = useMemo(() => {
    const visibleCandidates = (latestMatchingBatch?.engine_insight?.candidates ?? []).filter(
      (candidate) => candidate.direction !== "HOLD" && candidate.entry_price > 0
    );
    if (visibleCandidates.length > 0) {
      const topCandidate = visibleCandidates[0];
      return `The engine found ${visibleCandidates.length} chart setup${visibleCandidates.length > 1 ? "s" : ""} and marked them on the chart, but the primary decision stayed ${latestMatchingBatch?.primary.direction ?? "HOLD"} because ${topCandidate.blocker_reasons[0]?.message?.toLowerCase() ?? "the execution filters did not clear"}.`;
    }
    if (noTradeReasons.length > 0) return noTradeReasons[0]?.message ?? "The engine rejected the current price action.";
    if (!isConnected) return "MT5 is offline, so there is no live market feed yet.";
    if (!isSymbolMatch) return `MT5 is streaming ${currentSymbol} while the dashboard is set to ${activeSymbol}.`;
    if (isStale) return "The last MT5 tick is stale, so the feed needs to refresh before trusting the board.";
    if (price > 0) return "Live ticks are moving, but the engine does not see a qualified setup at this price.";
    return `Engine is listening for ${activeSymbol} ticks and waiting for the first valid price update.`;
  }, [latestMatchingBatch, noTradeReasons, isConnected, isSymbolMatch, currentSymbol, activeSymbol, isStale, price]);

  return (
    <div className="flex flex-col w-screen h-[100dvh] overflow-hidden bg-[#090b0f] text-text-primary antialiased">
      
      {/* ── TOP BAR (FLEX-NONE) ── */}
      <header className="flex-none min-h-[56px] py-2 z-30 flex flex-col md:flex-row md:items-center justify-between px-3 md:px-4 bg-[#0f1219] border-b border-white/5">
        {/* Left section: Logo & Symbol selector */}
        <div className="flex flex-row items-center justify-between w-full md:w-auto h-full">
          <div className="flex items-center gap-3 md:gap-4">
            <Link href="/" className="flex items-center gap-2 group">
              <div className="flex h-7 w-7 items-center justify-center rounded bg-gold/10 border border-gold/20 group-hover:border-gold/40 transition-colors">
                <TrendingUp className="h-4 w-4 text-gold" />
              </div>
              <h1 className="text-sm font-bold font-(family-name:--font-space-grotesk) text-linear-to-r from-gold to-amber-500 bg-clip-text text-transparent uppercase tracking-widest hidden sm:block">Midas</h1>
            </Link>
            
            <div className="h-4 w-px bg-white/10 hidden md:block" />
            
            <div className="flex items-center gap-2">
              <select
                value={targetSymbol}
                onChange={(e) => setTargetSymbol(e.target.value)}
                className="bg-[#1a202c] border border-white/20 rounded-md px-2.5 py-1 text-xs font-semibold text-white outline-none cursor-pointer focus:border-gold/50 transition-colors uppercase tracking-wide hover:bg-[#252b3b]"
              >
                <option value="XAUUSD">XAU/USD</option>
                <option value="XAGUSD">XAG/USD</option>
                <option value="BTCUSD">BTC/USD</option>
                <option value="EURUSD">EUR/USD</option>
                <option value="GBPUSD">GBP/USD</option>
              </select>

              {price > 0 && (
                <div className="flex md:hidden items-center gap-2 ml-1">
                  <span className="text-sm font-bold font-(family-name:--font-jetbrains-mono) text-white">
                    {formatPrice(price)}
                  </span>
                  <span className={`text-[10px] font-bold font-(family-name:--font-jetbrains-mono) px-1.5 py-0.5 rounded ${change >= 0 ? "bg-bullish/10 text-bullish" : "bg-bearish/10 text-bearish"} hidden sm:flex items-center gap-1`}>
                    {change >= 0 ? "▲" : "▼"} {Math.abs(change).toFixed(2)} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="hidden md:flex min-w-[280px] flex-col rounded-lg border border-white/5 bg-black/40 px-3 py-1.5 shadow-inner">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-bold font-(family-name:--font-jetbrains-mono) text-white">
                  {price > 0 ? formatPrice(price) : "--.--"}
                </span>
                <span className={`rounded-sm px-1.5 py-0.5 text-[10px] font-bold font-(family-name:--font-jetbrains-mono) ${change >= 0 ? "bg-bullish/10 text-bullish border border-bullish/20" : "bg-bearish/10 text-bearish border border-bearish/20"}`}>
                  {change >= 0 ? "+" : "-"}{Math.abs(change).toFixed(2)} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
                </span>
              </div>
              <div className="flex items-center gap-1.5 min-w-0">
                <div className={`h-1.5 w-1.5 rounded-full shrink-0 ${!isConnected ? "bg-bearish" : !isSymbolMatch || isStale ? "bg-warning" : "bg-bullish animate-pulse"}`} />
                <span className="text-[9px] text-white/40 truncate">
                  {livePriceError || liveStatusLabel}
                </span>
              </div>
            </div>
            
            <div className="mt-1 flex items-center justify-between">
              <div className="flex items-center gap-3 text-[10px] font-(family-name:--font-jetbrains-mono) text-white/50">
                <span className="flex items-center gap-1"><span className="text-text-muted">BID</span> {price > 0 ? formatPrice(livePrice?.bid ?? 0) : "--.--"}</span>
                <span className="flex items-center gap-1"><span className="text-text-muted">ASK</span> {price > 0 ? formatPrice(livePrice?.ask ?? 0) : "--.--"}</span>
                <span className="flex items-center gap-1"><span className="text-text-muted">SPR</span> {price > 0 ? spread.toFixed(2) : "--"}</span>
              </div>
            </div>
            
            {!isSymbolMatch && isConnected && (
              <div className="mt-1 text-[9px] text-warning/80 truncate">
                MT5 Symbol: {currentSymbol}
              </div>
            )}
          </div>

          {/* Mobile Right Actions */}
          <div className="flex md:hidden items-center gap-3">
             <div className="flex items-center gap-1.5">
              <div className={`h-1.5 w-1.5 rounded-full ${isConnected ? "bg-bullish animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.6)]" : "bg-white/20"}`} />
            </div>
            <Link href="/config" className="flex items-center justify-center p-1.5 rounded border border-white/10 text-white/50 bg-[#1a202c] hover:text-white">
              <Settings className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>

        {/* Center section: Controls */}
        <div className="hidden md:flex flex-row items-center justify-center gap-3 shrink-0">
          <div className="flex items-center bg-[#090b0f] p-1 rounded-md border border-white/5">
            {(["M1","M3","M5","M15","H1","H2","H4"] as Timeframe[]).map(tf => (
              <button key={tf} onClick={() => setTimeframe(tf)}
                className={`rounded px-2.5 py-1 text-[10px] font-semibold tracking-wide transition-all ${
                  tf === timeframe ? "bg-[#252b3b] text-white shadow-sm" : "text-white/40 hover:text-white/80 hover:bg-[#1a202c]"
                }`}>
                {tf}
              </button>
            ))}
          </div>
          <div className="flex items-center bg-[#090b0f] p-1 rounded-md border border-white/5">
            {(["Scalper","Intraday","Swing"] as const).map(s => (
              <button key={s} onClick={() => handleStyleChange(s)} disabled={styleChanging}
                className={`rounded px-3 py-1 text-[10px] font-semibold uppercase tracking-wider transition-all disabled:opacity-40 ${
                  s === tradingStyle ? "bg-gold/10 text-gold border border-gold/20 shadow-sm" : "text-white/40 hover:text-white/80 hover:bg-[#1a202c] border border-transparent"
                }`}>
                {styleChanging && s === tradingStyle ? "..." : s}
              </button>
            ))}
          </div>
        </div>

        {/* Right section: System Status */}
        <div className="hidden md:flex flex-row items-center gap-4 shrink-0">
          <div className="flex items-center gap-4 border-r border-white/10 pr-4">
            {[
              { icon: Trophy,  label: "WIN", value: perf.winRate + "%",  color: "text-bullish" },
              { icon: Target,  label: "SIG", value: String(perf.totalSignals), color: "text-white/80" },
              { icon: Percent, label: "P&L", value: (perf.todayPnl >= 0 ? "+" : "") + "$" + perf.todayPnl.toFixed(0), color: perf.todayPnl >= 0 ? "text-bullish" : "text-bearish" },
            ].map(({ icon: Icon, label, value, color }) => (
              <div key={label} className="flex items-center gap-1.5" title={`${label} today`}>
                <Icon className="h-3.5 w-3.5 text-white/30" />
                <span className="text-[9px] font-bold tracking-widest text-white/30">{label}</span>
                <span className={`text-[11px] font-bold font-(family-name:--font-jetbrains-mono) ${color}`}>{value}</span>
              </div>
            ))}
          </div>
          
          <div className="flex items-center gap-2 px-1">
            <div className={`h-2 w-2 rounded-full ${isConnected ? "bg-bullish animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.6)]" : "bg-bearish"}`} />
            <span className={`text-[10px] uppercase font-bold tracking-widest ${isConnected ? "text-bullish" : "text-bearish"}`}>
              {isConnected ? "Connected" : "Offline"}
            </span>
          </div>
          
          <Link href="/config" className="flex items-center justify-center p-1.5 rounded-md border border-white/10 bg-[#1a202c] text-white/50 hover:text-white hover:bg-[#252b3b] transition-all" title="System Settings">
            <Settings className="h-4 w-4" />
          </Link>

        </div>
      </header>

      {/* Mobile Controls Row (Only visible on small screens) */}
      <div className="flex md:hidden flex-none w-full bg-[#0f1219] px-2 py-1.5 border-b border-white/5 overflow-x-auto hide-scrollbar gap-2">
        <div className="shrink-0 rounded border border-white/10 bg-black/20 px-2 py-1">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold font-(family-name:--font-jetbrains-mono) text-white">
              {price > 0 ? formatPrice(price) : "--.--"}
            </span>
            <span className={`rounded px-1 py-0.5 text-[8px] font-bold font-(family-name:--font-jetbrains-mono) ${change >= 0 ? "bg-bullish/10 text-bullish" : "bg-bearish/10 text-bearish"}`}>
              {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
            </span>
          </div>
          <div className="mt-0.5 text-[8px] font-(family-name:--font-jetbrains-mono) text-white/35">
            BID {price > 0 ? formatPrice(livePrice?.bid ?? 0) : "--.--"} · ASK {price > 0 ? formatPrice(livePrice?.ask ?? 0) : "--.--"} · {livePriceError || liveStatusLabel}
          </div>
        </div>
        <div className="flex items-center bg-[#090b0f] p-1 rounded border border-white/5 shrink-0">
          {(["M1","M3","M5","M15","H1","H2","H4"] as Timeframe[]).map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              className={`rounded px-1.5 py-1 text-[9px] font-bold ${tf === timeframe ? "bg-[#252b3b] text-white" : "text-white/40"}`}>
              {tf}
            </button>
          ))}
        </div>
        <div className="flex items-center bg-[#090b0f] p-1 rounded border border-white/5 shrink-0">
          {(["Scalper","Intraday","Swing"] as const).map(s => (
            <button key={s} onClick={() => handleStyleChange(s)} disabled={styleChanging}
              className={`rounded px-2 flex-1 py-1 text-[9px] font-bold uppercase tracking-wider ${s === tradingStyle ? "bg-gold/10 text-gold" : "text-white/40"}`}>
              {styleChanging && s === tradingStyle ? "..." : s}
            </button>
          ))}
        </div>
      </div>

      {/* ── MAIN WORKSPACE (FLEX-1) ── */}
      <div className="flex-1 w-full flex flex-row overflow-hidden relative">
        
        {/* ── LEFT PANEL ── */}
        <aside 
          className={`
            absolute md:relative z-20 left-0 h-full shrink-0 w-[85vw] overflow-hidden
            transition-all duration-300 ease-in-out
            bg-[#0f1219] border-r border-white/5
            ${leftOpen 
              ? "translate-x-0 shadow-[20px_0_40px_rgba(0,0,0,0.5)] md:shadow-none md:w-[300px]" 
              : "-translate-x-full md:translate-x-0 md:w-0 md:pointer-events-none border-r-transparent"}
          `}
        >
          {/* Inner constraint so content doesn't squash when animating width */}
          <div className="h-full flex flex-col w-[85vw] md:w-[300px] overflow-hidden">
            {/* Mobile Header / Drag handle */}
            <div className="md:hidden flex items-center justify-between p-3 border-b border-white/5 bg-[#1a202c]">
              <h2 className="text-[10px] font-bold tracking-widest uppercase text-white/50">Midas Analysis</h2>
              <button className="text-white/50 p-1" onClick={() => setLeftOpen(false)}>×</button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-3 space-y-4">
              {/* Section: Status */}
              <AnalysisEngineCard
                tradingStyle={tradingStyle}
                isConnected={isConnected}
                nextAnalysis={nextAnalysis}
                lastAnalysis={lastAnalysis}
                targetSymbol={targetSymbol}
                price={price}
                livePrice={livePrice}
                spread={spread}
                lastTickLabel={lastTickLabel}
                livePriceError={livePriceError}
                liveStatusLabel={liveStatusLabel}
                isSymbolMatch={isSymbolMatch}
                isStale={isStale}
                configApiKey={config.apiKey}
                latestRegimeSummary={
                  latestBatch && latestBatch.trading_style.toLowerCase() === tradingStyle.toLowerCase()
                    ? latestBatch.regime_summary
                    : null
                }
              />

              {/* Section: Active Signal */}
              <div>
                <h2 className="text-[9px] font-bold text-white/40 uppercase tracking-widest pl-1 mb-2 block">Actionable Intelligence</h2>
                {displaySignal ? (
                  <>
                    <SignalCard signal={displaySignal} onExecute={handleExecuteSignal} />
                    {displayBackups.length > 0 && (
                      <div className="mt-3 rounded-lg border border-white/5 bg-[#131722] p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <p className="text-[9px] font-bold uppercase tracking-widest text-white/30">Backup Setups</p>
                          <span className="text-[9px] font-(family-name:--font-jetbrains-mono) text-white/20">
                            {latestBatch?.market_regime || displaySignal.market_regime || "regime"}
                          </span>
                        </div>
                        <div className="space-y-2">
                          {displayBackups.map((signal, index) => (
                            <div
                              key={signal.id || signal.signal_id || `${signal.analysis_batch_id}-${signal.rank ?? index}`}
                              className="rounded-md border border-white/5 bg-black/20 p-2"
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className={`text-[10px] font-bold ${signal.direction === "BUY" ? "text-bullish" : "text-bearish"}`}>
                                    {signal.direction}
                                  </span>
                                  <span className="text-[9px] uppercase tracking-wider text-white/30">
                                    {(signal.setup_type || "backup").replaceAll("_", " ")}
                                  </span>
                                </div>
                                <span className="text-[10px] font-(family-name:--font-jetbrains-mono) text-gold/80">
                                  {Math.round(signal.score ?? signal.confidence ?? 0)}
                                </span>
                              </div>
                              <div className="mt-1 text-[10px] text-white/55">
                                Entry {signal.entry_price} · SL {signal.stop_loss} · TP1 {signal.take_profit_1}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="space-y-3">
                    <div className="bg-[#131722] rounded-lg border border-white/5 p-6 flex flex-col items-center justify-center text-center relative overflow-hidden">
                      <div className="absolute inset-0 bg-gold/5 blur-3xl animate-pulse" />
                      <BarChart3 className="h-6 w-6 text-white/10 mb-3 relative z-10 animate-bounce" />
                      <p className="text-[11px] font-medium text-white/40 uppercase tracking-wider relative z-10 flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-gold animate-pulse" /> Engine Analyzing
                      </p>
                      <p className="text-[10px] text-white/30 mt-1 max-w-[220px] relative z-10">{noSetupMessage}</p>
                      {latestMatchingBatch?.regime_summary && (
                        <p className="mt-3 max-w-[240px] text-[10px] leading-relaxed text-white/40 relative z-10">
                          {latestMatchingBatch.regime_summary}
                        </p>
                      )}
                      {noTradeReasons.length > 1 && (
                        <div className="mt-3 w-full max-w-[260px] rounded-md border border-white/5 bg-black/20 p-3 text-left relative z-10">
                          <p className="text-[9px] font-bold uppercase tracking-widest text-white/25">Engine Reasons</p>
                          <div className="mt-2 space-y-1.5">
                            {noTradeReasons.slice(0, 3).map((reason, index) => (
                              <p key={`${reason.code}-${index}`} className="text-[10px] leading-relaxed text-white/40">
                                {reason.blocking ? "Blocker:" : "Context:"} {reason.message}
                              </p>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                    {/* Expose MarketState explicitly when no setup is active so user sees live tick data flowing */}
                    <div className="hidden md:block">
                      <h2 className="text-[9px] font-bold text-white/40 uppercase tracking-widest pl-1 mb-2 block mt-2">Live Regime Context</h2>
                      <MarketStatePanel />
                    </div>
                  </div>
                )}
              </div>
              
              {false && <div className="bg-[#131722] rounded-lg border border-white/5 p-3">
                <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2">
                  <p className="text-[9px] font-bold text-white/30 uppercase tracking-widest">Metrics / Performance</p>
                  <button
                    onClick={resetPerformance}
                    disabled={resetting}
                    className="flex items-center gap-1 rounded bg-black/20 px-1.5 py-1 text-[9px] font-bold text-white/20 hover:text-bearish hover:bg-bearish/10 border border-transparent hover:border-bearish/20 transition-all disabled:opacity-40 uppercase tracking-wider"
                    title="Reset all performance stats"
                  >
                    {resetting ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Trash2 className="h-2.5 w-2.5" />}
                    {resetting ? "Resetting..." : "Reset"}
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { label: "Win Rate",  value: perf.winRate + "%",  color: "text-bullish" },
                    { label: "P.Factor",  value: perf.profitFactor > 0 ? perf.profitFactor + "x" : "—", color: "text-gold" },
                    { label: "Today PnL", value: (perf.todayPnl >= 0 ? "+" : "") + "$" + perf.todayPnl.toFixed(0), color: perf.todayPnl >= 0 ? "text-bullish" : "text-bearish" },
                    { label: "Week PnL",  value: (perf.weekPnl >= 0 ? "+" : "") + "$" + perf.weekPnl.toFixed(0),   color: perf.weekPnl >= 0 ? "text-bullish" : "text-bearish" },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="bg-white/5 p-2 rounded flex flex-col justify-between">
                      <p className="text-[9px] font-bold uppercase tracking-widest text-white/30 mb-1">{label}</p>
                      <p className={`text-xs font-bold font-(family-name:--font-jetbrains-mono) ${color}`}>{value}</p>
                    </div>
                  ))}
                </div>
              </div>}
            </div>
          </div>
        </aside>

        {/* ── CHART AREA (FLEX-1) ── */}
        <main className="flex-1 w-full min-w-0 h-full relative flex flex-col bg-[#090b0f]">
          
          {/* Overlay Offline Alert */}
          {!isConnected && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[40] bg-bearish/20 border border-bearish/40 px-4 py-2 rounded shadow-2xl backdrop-blur-md flex items-center gap-3 animate-in fade-in slide-in-from-top-4 duration-500 pointer-events-none">
              <div className="h-2 w-2 rounded-full bg-bearish animate-ping" />
              <span className="text-[10px] font-bold text-white tracking-widest uppercase">MT5 Terminal Offline</span>
            </div>
          )}

          {/* Desktop Panel Toggles Overlay */}
          <button onClick={() => setLeftOpen(o => !o)}
            className="hidden md:flex absolute left-0 top-1/2 -translate-y-1/2 z-10 w-4 h-12 flex-col items-center justify-center bg-[#0f1219]/90 border border-l-0 border-white/10 rounded-r hover:bg-white/10 hover:w-5 transition-all text-white/40 hover:text-white group">
            <div className="w-0.5 h-3 bg-white/20 rounded-full group-hover:bg-white/40 mb-1" />
            {leftOpen ? <ChevronLeft className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          </button>
          
          <button onClick={() => setRightOpen(o => !o)}
            className="hidden md:flex absolute right-0 top-1/2 -translate-y-1/2 z-10 w-4 h-12 flex-col items-center justify-center bg-[#0f1219]/90 border border-r-0 border-white/10 rounded-l hover:bg-white/10 hover:w-5 transition-all text-white/40 hover:text-white group">
            <div className="w-0.5 h-3 bg-white/20 rounded-full group-hover:bg-white/40 mb-1" />
            {rightOpen ? <ChevronRight className="h-3 w-3" /> : <ChevronLeft className="h-3 w-3" />}
          </button>

          {/* Mobile Panel Toggles */}
          <div className="md:hidden absolute bottom-4 right-4 z-40 flex flex-col gap-2">
             <button onClick={() => setRightOpen(true)} className="h-10 w-10 rounded-full bg-gold/90 text-black flex items-center justify-center shadow-lg backdrop-blur">
               <Activity className="h-4 w-4" />
             </button>
             <button onClick={() => setLeftOpen(true)} className="h-10 w-10 rounded-full bg-[#1a202c]/90 border border-white/10 text-white flex items-center justify-center shadow-lg backdrop-blur">
               <TrendingUp className="h-4 w-4" />
             </button>
          </div>

          {/* Chart Wrapper - flex-1 shrinks/grows to available space */}
          <div className="flex-1 w-full relative z-0 min-h-[300px] border-b border-white/5">
            {candlesLoading ? (
              <div className="absolute inset-0 flex items-center justify-center bg-[#131722]">
                <BarChart3 className="h-10 w-10 text-white/10 animate-pulse" />
              </div>
            ) : (
              <div className="absolute inset-0">
                <TradingViewChart
                  data={candleData}
                  lines={chartLines}
                  legendItems={chartLegendItems}
                />
              </div>
            )}
          </div>

          {/* ── EXECUTION TERMINAL (BOTTOM PANEL) ── */}
          <div 
            className="flex-none bg-[#0a0d14] flex flex-col relative z-20"
            style={{ height: bottomPanelHeight }}
          >
            {/* Drag Handle */}
            <div 
              onPointerDown={handlePointerDown}
              className="absolute top-0 inset-x-0 h-4 -translate-y-1/2 cursor-row-resize z-50 group flex items-center justify-center"
            >
              <div className={`w-12 h-1 rounded-full transition-colors ${isResizing ? "bg-gold" : "bg-white/10 group-hover:bg-gold/50"}`} />
            </div>

            <div className="flex items-center justify-between px-3 py-2 border-b border-white/5 bg-[#0f1219]">
              <h2 className="text-[10px] font-bold tracking-widest uppercase text-white/50 flex items-center gap-2">
                <Terminal className="h-3 w-3" /> System Terminal
              </h2>
              <div className="flex items-center gap-2">
                <div className="hidden md:flex items-center gap-1 rounded-md border border-white/10 bg-black/20 p-1">
                  {([
                    { id: "terminal", label: "Execution Log", icon: Terminal },
                    { id: "market-state", label: "Market State", icon: Activity },
                    { id: "performance", label: "Performance", icon: Trophy },
                  ] as { id: BottomTab; label: string; icon: typeof Terminal }[]).map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setBottomTab(tab.id)}
                      className={`flex items-center gap-1 rounded px-2 py-1 text-[9px] font-bold uppercase tracking-wider transition-all ${
                        bottomTab === tab.id
                          ? "bg-gold/10 text-gold border border-gold/20"
                          : "text-white/30 hover:bg-white/5 hover:text-white/70 border border-transparent"
                      }`}
                    >
                      <tab.icon className="h-3 w-3" />
                      {tab.label}
                    </button>
                  ))}
                </div>
                <div className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse max-md:hidden" />
                <span className="text-[9px] font-(family-name:--font-jetbrains-mono) text-bullish tracking-wider hidden md:inline">SYSTEM.ACTIVE</span>
              </div>
            </div>

            <div className="flex md:hidden items-center gap-1 border-b border-white/5 bg-[#0c1017] px-2 py-1.5">
              {([
                { id: "terminal", label: "Logs", icon: Terminal },
                { id: "market-state", label: "State", icon: Activity },
                { id: "performance", label: "Perf", icon: Trophy },
              ] as { id: BottomTab; label: string; icon: typeof Terminal }[]).map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setBottomTab(tab.id)}
                  className={`flex items-center gap-1 rounded px-2 py-1 text-[9px] font-bold uppercase tracking-wider transition-all ${
                    bottomTab === tab.id
                      ? "bg-gold/10 text-gold border border-gold/20"
                      : "text-white/35 hover:bg-white/5 hover:text-white/70 border border-transparent"
                  }`}
                >
                  <tab.icon className="h-3 w-3" />
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto p-2 hide-scrollbar">
              {bottomTab === "terminal" && (
                <div className="space-y-1 font-(family-name:--font-jetbrains-mono) text-[10px]">
                  {displayHistory.slice(0, 15).map((sig, idx) => (
                    <div key={`${sig.id || sig.timestamp || idx}-${sig.symbol}-${idx}`} className="flex items-center gap-3 hover:bg-white/5 p-1 rounded transition-colors group">
                      <span className="text-white/20 whitespace-nowrap hidden sm:inline">
                        {sig.timestamp ? new Date(sig.timestamp).toLocaleTimeString() : "--:--:--"}
                      </span>
                      <span className={`font-bold w-12 shrink-0 ${sig.direction === 'BUY' ? 'text-bullish' : sig.direction === 'SELL' ? 'text-bearish' : 'text-warning'}`}>
                        [{sig.direction}]
                      </span>
                      <span className="text-white/60 truncate flex-1 min-w-0">
                        {sig.symbol || targetSymbol} <span className="text-white/40">at</span> {sig.entry_price} <span className="text-white/40 ml-1">SL: {sig.stop_loss}</span> <span className="text-white/40 ml-1">TP: {sig.take_profit_1}</span>
                      </span>
                    </div>
                  ))}
                  {displayHistory.length === 0 && (
                    <div className="text-white/20 p-2 italic flex items-center justify-center h-full min-h-32">Waiting for signal execution commands...</div>
                  )}
                </div>
              )}

              {bottomTab === "market-state" && (
                <div className="w-full h-full">
                  <MarketStatePanel />
                </div>
              )}

              {bottomTab === "performance" && (
                <PerformancePanel perf={perf} resetting={resetting} resetPerformance={resetPerformance} />
              )}

              {false && bottomTab === "performance" && (
                <div className="bg-[#131722] rounded-lg border border-white/5 p-3">
                  <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2">
                    <p className="text-[9px] font-bold text-white/30 uppercase tracking-widest">Metrics / Performance</p>
                    <button
                      onClick={resetPerformance}
                      disabled={resetting}
                      className="flex items-center gap-1 rounded bg-black/20 px-1.5 py-1 text-[9px] font-bold text-white/20 hover:text-bearish hover:bg-bearish/10 border border-transparent hover:border-bearish/20 transition-all disabled:opacity-40 uppercase tracking-wider"
                      title="Reset all performance stats"
                    >
                      {resetting ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Trash2 className="h-2.5 w-2.5" />}
                      {resetting ? "Resetting..." : "Reset"}
                    </button>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {[
                      { label: "Win Rate", value: perf.winRate + "%", color: "text-bullish" },
                      { label: "P.Factor", value: perf.profitFactor > 0 ? perf.profitFactor + "x" : "—", color: "text-gold" },
                      { label: "Today PnL", value: (perf.todayPnl >= 0 ? "+" : "") + "$" + perf.todayPnl.toFixed(0), color: perf.todayPnl >= 0 ? "text-bullish" : "text-bearish" },
                      { label: "Week PnL", value: (perf.weekPnl >= 0 ? "+" : "") + "$" + perf.weekPnl.toFixed(0), color: perf.weekPnl >= 0 ? "text-bullish" : "text-bearish" },
                    ].map(({ label, value, color }) => (
                      <div key={label} className="bg-white/5 p-3 rounded flex flex-col justify-between min-h-20">
                        <p className="text-[9px] font-bold uppercase tracking-widest text-white/30 mb-1">{label}</p>
                        <p className={`text-sm font-bold font-(family-name:--font-jetbrains-mono) ${color}`}>{value}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </main>

        {/* ── RIGHT PANEL ── */}
        <aside 
          className={`
            absolute md:relative z-20 right-0 h-full shrink-0 w-[85vw] overflow-hidden
            transition-all duration-300 ease-in-out
            bg-[#0f1219] border-l border-white/5
            ${rightOpen 
              ? "translate-x-0 shadow-[-20px_0_40px_rgba(0,0,0,0.5)] md:shadow-none md:w-[320px]" 
              : "translate-x-full md:translate-x-0 md:w-0 md:pointer-events-none border-l-transparent"}
          `}
        >
          {/* Inner constraint */}
          <div className="h-full flex flex-col w-[85vw] md:w-[320px] overflow-hidden">
            {/* Mobile Header / Drag handle */}
            <div className="md:hidden flex items-center justify-between p-3 border-b border-white/5 bg-[#1a202c]">
              <h2 className="text-[10px] font-bold tracking-widest uppercase text-white/50">Market Intelligence</h2>
              <button className="text-white/50 p-1" onClick={() => setRightOpen(false)}>×</button>
            </div>

            {/* Terminal-style Tabs */}
            <div className="flex border-b border-white/5 bg-[#0b0e14] shrink-0 h-10">
              {([
                { id: "engine",   label: "ENGINE",   icon: Activity     },
                { id: "news",     label: "NEWS",     icon: Newspaper    },
                { id: "calendar", label: "MACRO",    icon: CalendarDays },
                { id: "history",  label: "LOGS",     icon: History      },
              ] as { id: RightTab; label: string; icon: typeof Newspaper }[]).map(t => (
                <button key={t.id} onClick={() => setRightTab(t.id)}
                  className={`flex-1 flex items-center justify-center gap-1.5 text-[9px] font-bold uppercase tracking-widest transition-all border-b-2 ${
                    rightTab === t.id ? "border-gold text-gold bg-gold/5" : "border-transparent text-white/30 hover:text-white/60 hover:bg-white/5"
                  }`}>
                  <t.icon className="h-3 w-3 opacity-70" /> {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="flex-1 overflow-y-auto p-3 bg-[#0f1219]">
              {rightTab === "engine" && (
                <EngineInsightPanel
                  batch={latestMatchingBatch}
                  marketState={marketState}
                  noSetupMessage={noSetupMessage}
                />
              )}
              {rightTab === "news" && (
                newsLoading
                  ? <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <div key={`news-skel-${i}`} className="h-20 rounded bg-white/5 animate-pulse" />)}</div>
                  : <NewsSentiment items={newsItems} />
              )}
              {rightTab === "calendar" && (
                calendarLoading
                  ? <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <div key={`cal-skel-${i}`} className="h-16 rounded bg-white/5 animate-pulse" />)}</div>
                  : <EconomicCalendar events={calendarEvents} />
              )}
              {rightTab === "history" && (
                historyLoading
                  ? <div className="space-y-2">{Array.from({ length: 4 }).map((_, i) => <div key={`hist-skel-${i}`} className="h-12 rounded bg-white/5 animate-pulse" />)}</div>
                  : (
                    <>
                      {displayHistory.length > 0 && (
                        <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2">
                          <span className="text-[9px] font-bold tracking-widest text-white/30 uppercase">{displayHistory.length} Record{displayHistory.length === 1 ? "" : "s"}</span>
                          <button
                            onClick={clearHistory}
                            disabled={clearing}
                            className="flex items-center gap-1 rounded bg-black/20 px-1.5 py-1 text-[9px] font-bold text-bearish/50 hover:text-bearish hover:bg-bearish/10 border border-transparent hover:border-bearish/20 transition-all disabled:opacity-40 uppercase tracking-widest"
                          >
                            {clearing ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <Trash2 className="h-2.5 w-2.5" />}
                            {clearing ? "Purging..." : "Clear"}
                          </button>
                        </div>
                      )}
                      <SignalHistory signals={displayHistory} />
                    </>
                  )
              )}
            </div>
          </div>
        </aside>

      </div>
    </div>
  );
}
