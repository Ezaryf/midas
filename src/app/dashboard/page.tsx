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
import { useSignalPersistence } from "@/hooks/useSignalPersistence";
import { useSignalHistory } from "@/hooks/useSignalHistory";
import { usePerformance } from "@/hooks/usePerformance";
import { useSignalTracker } from "@/hooks/useSignalTracker";
import { useLivePrice } from "@/hooks/useLivePrice";
import {
  TrendingUp, Settings, Newspaper, CalendarDays, History,
  BarChart3, Trophy, Target, Percent, Trash2, ChevronLeft, ChevronRight, Loader2,
} from "lucide-react";
import { formatPrice } from "@/lib/utils";
import { LineStyle } from "lightweight-charts";
import SignalCard from "@/components/signals/SignalCard";
import SignalHistory from "@/components/signals/SignalHistory";
import NewsSentiment from "@/components/data/NewsSentiment";
import EconomicCalendar from "@/components/data/EconomicCalendar";
import SignOutButton from "@/components/auth/SignOutButton";

const TradingViewChart = dynamic(
  () => import("@/components/chart/TradingViewChart"),
  { ssr: false, loading: () => <div className="w-full h-full bg-transparent" /> }
);

type RightTab = "news" | "calendar" | "history";

export default function DashboardPage() {
  // Persist timeframe & tradingStyle in localStorage so they survive navigation
  const [timeframe, setTimeframeRaw] = useState<Timeframe>(() => {
    if (typeof window === "undefined") return "M15";
    try {
      const saved = localStorage.getItem("midas_timeframe") as Timeframe | null;
      if (saved && ["M1","M3","M5","M15","H1","H4"].includes(saved)) return saved;
    } catch { /* ignore */ }
    return "M15";
  });
  const [tradingStyle, setTradingStyleRaw] = useState<"Scalper" | "Intraday" | "Swing">(() => {
    if (typeof window === "undefined") return "Scalper";
    try {
      const saved = localStorage.getItem("midas_trading_style") as "Scalper" | "Intraday" | "Swing" | null;
      if (saved && ["Scalper","Intraday","Swing"].includes(saved)) return saved;
    } catch { /* ignore */ }
    return "Scalper";
  });
  const [styleChanging, setStyleChanging] = useState(false);
  const [rightTab, setRightTab]       = useState<RightTab>("news");
  const [rightOpen, setRightOpen]     = useState(true);
  const [leftOpen, setLeftOpen]       = useState(true);
  const [lastAnalysis, setLastAnalysis] = useState<Date | null>(null);
  const [nextAnalysis, setNextAnalysis] = useState<number>(10);

  // Wrapped setters that also persist
  const setTimeframe = useCallback((tf: Timeframe) => {
    setTimeframeRaw(tf);
    try { localStorage.setItem("midas_timeframe", tf); } catch { /* ignore */ }
  }, []);

  const setTradingStyle = useCallback((style: "Scalper" | "Intraday" | "Swing") => {
    setTradingStyleRaw(style);
    try { localStorage.setItem("midas_trading_style", style); } catch { /* ignore */ }
  }, []);

  useSocket();
  useSignalPersistence();
  useSignalTracker();
  const { activeSignal, signalHistory, isConnected, clearActiveSignal } = useMidasStore();
  
  // Track when signals arrive (automatic analysis indicator)
  useEffect(() => {
    if (activeSignal) {
      // Use a microtask to avoid cascading renders
      Promise.resolve().then(() => setLastAnalysis(new Date()));
    }
  }, [activeSignal]);
  const { config } = useConfig();
  const { stats: perf, resetting, resetPerformance } = usePerformance();
  const { data: livePrice } = useLivePrice();
  
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

  const handleStyleChange = useCallback(async (style: "Scalper" | "Intraday" | "Swing") => {
    if (style === tradingStyle) return;
    setStyleChanging(true);
    setTradingStyle(style);
    clearActiveSignal();
    // Clear history that doesn't match the new style
    useMidasStore.setState((s) => ({
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
      await fetch("/api/signals/force-generate", {
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
    const base = dbHistory.length > 0 ? dbHistory : signalHistory;
    // For chart lines, prefer style-matched signals — but keep all for history tab
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

  // No manual generation needed - system is fully automatic via WebSocket

  const chartLines = useMemo(() => {
    const lines: Array<{ price: number; color: string; label: string; style: LineStyle }> = [];
    const COLORS = [
      { entry: "#F59E0B", sl: "#EF4444", tp: "#22C55E" },
      { entry: "#60A5FA", sl: "#F87171", tp: "#34D399" },
      { entry: "#C084FC", sl: "#FB923C", tp: "#4ADE80" },
      { entry: "#F472B6", sl: "#FCA5A5", tp: "#6EE7B7" },
    ];

    const active = displayHistory.filter(s =>
      s.status !== "STOPPED" && s.status !== "HIT_TP1" && s.status !== "HIT_TP2" &&
      s.entry_price && s.stop_loss && s.take_profit_1 && s.take_profit_2
    );
    // STRICT: only show lines for signals matching the current trading style
    const pool = active.filter(s => s.trading_style?.toLowerCase() === tradingStyle.toLowerCase());

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
    const top4 = [...unique]
      .sort((a, b) => {
        if (currentPx > 0) {
          const distA = Math.abs(a.entry_price - currentPx);
          const distB = Math.abs(b.entry_price - currentPx);
          if (Math.abs(distA - distB) > 1) return distA - distB; // closest first
        }
        return (b.confidence ?? 0) - (a.confidence ?? 0); // tie-break by confidence
      })
      .slice(0, 4);

    top4.forEach((sig, idx) => {
      const c = COLORS[idx];
      // Short labels — axis already shows the price number
      const n = top4.length > 1 ? `${idx + 1}` : "";
      lines.push(
        { price: sig.entry_price,   color: c.entry, label: `E${n}`,   style: LineStyle.Solid  },
        { price: sig.stop_loss,     color: c.sl,    label: `SL${n}`,  style: LineStyle.Dashed },
        { price: sig.take_profit_1, color: c.tp,    label: `TP1${n}`, style: LineStyle.Dashed },
        { price: sig.take_profit_2, color: c.tp,    label: `TP2${n}`, style: LineStyle.Dotted },
      );
    });

    return lines;
  }, [displayHistory, tradingStyle, livePrice?.price]);

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

  const LEFT_W   = 300;
  const RIGHT_W  = 320;
  const HEADER_H = 44;
  const chartLeft  = leftOpen  ? LEFT_W  + 8 : 0;
  const chartRight = rightOpen ? RIGHT_W + 8 : 0;

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-background">

      {/* ── FULL-SCREEN CHART — starts below header ── */}
      <div
        className="absolute bottom-0 transition-all duration-300"
        style={{ top: HEADER_H, left: chartLeft, right: chartRight }}
      >
        {candlesLoading ? (
          <div className="w-full h-full flex items-center justify-center">
            <BarChart3 className="h-10 w-10 text-text-muted/20 animate-pulse" />
          </div>
        ) : (
          <TradingViewChart
            data={candleData}
            lines={chartLines}
            height={typeof window !== "undefined" ? window.innerHeight - HEADER_H : 860}
          />
        )}
      </div>

      {/* ── TOP BAR ── */}
      <div className="absolute top-0 left-0 right-0 z-30 flex items-center justify-between px-4 py-2.5"
        style={{ background: "linear-gradient(to bottom, rgba(9,9,11,0.92) 0%, rgba(9,9,11,0) 100%)" }}>

        {/* Left: Logo + price */}
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gold/10 border border-gold/20">
              <TrendingUp className="h-3.5 w-3.5 text-gold" />
            </div>
            <span className="text-sm font-bold font-[family-name:var(--font-space-grotesk)] text-gradient-gold">Midas</span>
          </Link>
          <div className="h-4 w-px bg-white/10" />
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">XAU/USD</span>
            {price > 0 && (
              <>
                <span className="text-sm font-bold font-[family-name:var(--font-jetbrains-mono)] text-white">
                  {formatPrice(price)}
                </span>
                <span className={`text-xs font-medium font-[family-name:var(--font-jetbrains-mono)] ${change >= 0 ? "text-bullish" : "text-bearish"}`}>
                  {change >= 0 ? "+" : ""}{change.toFixed(2)} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
                </span>
              </>
            )}
          </div>
        </div>

        {/* Center: Timeframe + Style */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-0.5 rounded-lg bg-black/40 backdrop-blur-sm border border-white/10 p-1">
            {(["M1","M3","M5","M15","H1","H4"] as Timeframe[]).map(tf => (
              <button key={tf} onClick={() => setTimeframe(tf)}
                className={`rounded-md px-2.5 py-1 text-[10px] font-medium transition-all ${
                  tf === timeframe ? "bg-gold/20 text-gold border border-gold/30" : "text-white/40 hover:text-white/70"
                }`}>{tf}</button>
            ))}
          </div>
          <div className="flex items-center gap-0.5 rounded-lg bg-black/40 backdrop-blur-sm border border-white/10 p-1">
            {(["Scalper","Intraday","Swing"] as const).map(s => (
              <button key={s} onClick={() => handleStyleChange(s)} disabled={styleChanging}
                className={`rounded-md px-2.5 py-1 text-[10px] font-medium transition-all disabled:opacity-40 ${
                  s === tradingStyle ? "bg-gold/20 text-gold border border-gold/30" : "text-white/40 hover:text-white/70"
                }`}>{styleChanging && s === tradingStyle ? "..." : s}</button>
            ))}
          </div>
        </div>

        {/* Right: Stats + actions */}
        <div className="flex items-center gap-3">
          <div className="hidden lg:flex items-center gap-3">
            {[
              { icon: Trophy,  label: "Win", value: perf.winRate + "%",  color: "text-bullish" },
              { icon: Target,  label: "Sig", value: String(perf.totalSignals), color: "text-white" },
              { icon: Percent, label: "P&L", value: (perf.todayPnl >= 0 ? "+" : "") + "$" + perf.todayPnl.toFixed(0), color: perf.todayPnl >= 0 ? "text-bullish" : "text-bearish" },
            ].map(({ icon: Icon, label, value, color }) => (
              <div key={label} className="flex items-center gap-1.5">
                <Icon className="h-3 w-3 text-white/30" />
                <span className="text-[10px] text-white/40">{label}</span>
                <span className={`text-[10px] font-bold font-[family-name:var(--font-jetbrains-mono)] ${color}`}>{value}</span>
              </div>
            ))}
          </div>
          <div className="h-4 w-px bg-white/10" />
          <div className="flex items-center gap-1.5">
            <div className={`h-1.5 w-1.5 rounded-full ${isConnected ? "bg-bullish animate-pulse" : "bg-white/20"}`} />
            <span className="text-[10px] text-white/40">{isConnected ? "Live" : "Offline"}</span>
          </div>
          <Link href="/config" className="flex items-center gap-1 rounded-lg bg-white/5 border border-white/10 px-2.5 py-1.5 text-[10px] text-white/50 hover:text-white/80 hover:bg-white/10 transition-all">
            <Settings className="h-3 w-3" /><span className="hidden sm:inline">Settings</span>
          </Link>
          <SignOutButton />
        </div>
      </div>

      {/* ── LEFT PANEL — glassmorphism overlay ── */}
      <div className={`absolute bottom-0 left-0 z-20 flex transition-all duration-300 ${leftOpen ? "translate-x-0" : "-translate-x-full"}`}
        style={{ top: HEADER_H, width: LEFT_W }}>
        <div className="flex-1 overflow-y-auto p-3 space-y-3 m-2 rounded-2xl"
          style={{ background: "rgba(9,9,11,0.75)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.06)" }}>

          {/* Auto-analysis status */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-medium text-white/40 uppercase tracking-wider">Auto Analysis</span>
              <span className="text-[9px] text-white/25 bg-white/5 px-1.5 py-0.5 rounded uppercase">{tradingStyle}</span>
            </div>
            <div className="flex items-center gap-2">
              {isConnected ? (
                <>
                  <div className="flex items-center gap-1">
                    <div className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse" />
                    <span className="text-[9px] text-bullish">Active</span>
                  </div>
                  <span className="text-[9px] text-white/30">Next: {nextAnalysis}s</span>
                </>
              ) : (
                <div className="flex items-center gap-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-bearish" />
                  <span className="text-[9px] text-bearish">Offline</span>
                </div>
              )}
            </div>
          </div>

          {lastAnalysis && (
            <div className="text-[9px] text-white/30">
              Last analysis: {lastAnalysis.toLocaleTimeString()}
            </div>
          )}
          
          {!config.apiKey && <p className="text-[9px] text-warning">No API key — <a href="/config" className="underline">Settings</a></p>}

          {/* Signal card */}
          {displaySignal ? (
            <SignalCard signal={displaySignal} onExecute={handleExecuteSignal} />
          ) : (
            <div className="rounded-xl border border-white/5 p-6 text-center">
              <BarChart3 className="h-6 w-6 text-gold/40 mx-auto mb-2" />
              <p className="text-xs text-white/30">No active signal</p>
              <p className="text-[10px] text-white/20 mt-1">Waiting for analysis...</p>
            </div>
          )}

          {/* Performance */}
          <div className="rounded-xl border border-white/5 p-3">
            <div className="flex items-center justify-between mb-2.5">
              <p className="text-[10px] font-medium text-white/30 uppercase tracking-wider">Performance</p>
              <button
                onClick={resetPerformance}
                disabled={resetting}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-[9px] text-white/25 hover:text-bearish hover:bg-bearish/10 transition-all disabled:opacity-40"
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
                { label: "Today",     value: (perf.todayPnl >= 0 ? "+" : "") + "$" + perf.todayPnl.toFixed(0), color: perf.todayPnl >= 0 ? "text-bullish" : "text-bearish" },
                { label: "Week",      value: (perf.weekPnl >= 0 ? "+" : "") + "$" + perf.weekPnl.toFixed(0),   color: perf.weekPnl >= 0 ? "text-bullish" : "text-bearish" },
              ].map(({ label, value, color }) => (
                <div key={label} className="rounded-lg bg-white/3 px-2.5 py-2">
                  <p className="text-[9px] text-white/25 mb-0.5">{label}</p>
                  <p className={`text-xs font-bold font-[family-name:var(--font-jetbrains-mono)] ${color}`}>{value}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Toggle tab */}
        <button onClick={() => setLeftOpen(o => !o)}
          className="absolute -right-6 top-1/2 -translate-y-1/2 flex h-12 w-6 items-center justify-center rounded-r-lg"
          style={{ background: "rgba(9,9,11,0.75)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.06)", borderLeft: "none" }}>
          {leftOpen ? <ChevronLeft className="h-3 w-3 text-white/30" /> : <ChevronRight className="h-3 w-3 text-white/30" />}
        </button>
      </div>

      {/* ── RIGHT PANEL — glassmorphism overlay ── */}
      <div className={`absolute bottom-0 right-0 z-20 flex flex-row-reverse transition-all duration-300 ${rightOpen ? "translate-x-0" : "translate-x-full"}`}
        style={{ top: HEADER_H, width: RIGHT_W }}>
        <div className="flex-1 flex flex-col overflow-hidden m-2 rounded-2xl"
          style={{ background: "rgba(9,9,11,0.75)", backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.06)" }}>

          {/* Tabs */}
          <div className="flex border-b border-white/5 shrink-0">
            {([
              { id: "news",     label: "News",     icon: Newspaper    },
              { id: "calendar", label: "Calendar", icon: CalendarDays },
              { id: "history",  label: "History",  icon: History      },
            ] as { id: RightTab; label: string; icon: typeof Newspaper }[]).map(t => (
              <button key={t.id} onClick={() => setRightTab(t.id)}
                className={`flex-1 flex items-center justify-center gap-1 py-2.5 text-[10px] font-medium transition-all border-b-2 ${
                  rightTab === t.id ? "border-gold text-gold" : "border-transparent text-white/30 hover:text-white/50"
                }`}>
                <t.icon className="h-3 w-3" />{t.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-3">
            {rightTab === "news" && (
              newsLoading
                ? <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-16 rounded-xl bg-white/3 animate-pulse" />)}</div>
                : <NewsSentiment items={newsItems} />
            )}
            {rightTab === "calendar" && (
              calendarLoading
                ? <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-16 rounded-xl bg-white/3 animate-pulse" />)}</div>
                : <EconomicCalendar events={calendarEvents} />
            )}
            {rightTab === "history" && (
              historyLoading
                ? <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-12 rounded-xl bg-white/3 animate-pulse" />)}</div>
                : (
                  <>
                    {displayHistory.length > 0 && (
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] text-white/30">{displayHistory.length} signal{displayHistory.length !== 1 ? "s" : ""}</span>
                        <button
                          onClick={clearHistory}
                          disabled={clearing}
                          className="flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] text-bearish/70 hover:text-bearish hover:bg-bearish/10 transition-all disabled:opacity-40"
                        >
                          {clearing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Trash2 className="h-3 w-3" />}
                          {clearing ? "Clearing..." : "Clear all"}
                        </button>
                      </div>
                    )}
                    <SignalHistory signals={displayHistory} />
                  </>
                )
            )}
          </div>
        </div>

        {/* Toggle tab */}
        <button onClick={() => setRightOpen(o => !o)}
          className="absolute -left-6 top-1/2 -translate-y-1/2 flex h-12 w-6 items-center justify-center rounded-l-lg"
          style={{ background: "rgba(9,9,11,0.75)", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.06)", borderRight: "none" }}>
          {rightOpen ? <ChevronRight className="h-3 w-3 text-white/30" /> : <ChevronLeft className="h-3 w-3 text-white/30" />}
        </button>
      </div>

    </div>
  );
}