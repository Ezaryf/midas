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
  BarChart3, Trophy, Target, Percent, Trash2, ChevronLeft, ChevronRight, Loader2, Terminal
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

type TradingStyle = "Scalper" | "Intraday" | "Swing";

export default function DashboardPage() {
  // Persist timeframe & tradingStyle in localStorage so they survive navigation
  const [timeframe, setTimeframeRaw] = useState<Timeframe>("H2");
  const [tradingStyle, setTradingStyleRaw] = useState<TradingStyle>("Scalper");
  const [styleChanging, setStyleChanging] = useState(false);
  const [rightTab, setRightTab]       = useState<RightTab>("news");
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
      } catch {}
    });
  }, []);

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
  useSignalPersistence();
  useSignalTracker();
  const { activeSignal, signalHistory, isConnected, clearActiveSignal, targetSymbol, setTargetSymbol } = useMidasStore();
  
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

  const handleStyleChange = useCallback(async (style: TradingStyle) => {
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
    // ALWAYS prioritize local state signals first if Supabase is a problem
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

  // No manual generation needed - system is fully automatic via WebSocket

  const chartLines = useMemo(() => {
    const lines: Array<{ price: number; color: string; label: string; style: LineStyle }> = [];
    const MAX_CHART_SIGNALS = 8;
    // Dynamic color generator — HSL rotation for unlimited distinct colors
    const generateColor = (idx: number) => ({
      entry: `hsl(${(idx * 47) % 360}, 70%, 65%)`,
      sl:    `hsl(${(idx * 47 + 15) % 360}, 80%, 55%)`,
      tp:    `hsl(${(idx * 47 + 120) % 360}, 70%, 60%)`,
    });

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
  }, [displayHistory, tradingStyle, livePrice?.price, targetSymbol]);

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

  return (
    <div className="flex flex-col w-screen h-[100dvh] overflow-hidden bg-[#090b0f] text-text-primary antialiased">
      
      {/* ── TOP BAR (FLEX-NONE) ── */}
      <header className="flex-none h-12 z-30 flex flex-col md:flex-row md:items-center justify-between px-3 md:px-4 bg-[#0f1219] border-b border-white/5">
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
                className="bg-[#1a202c] border border-white/10 rounded px-2 py-1 text-xs font-medium text-white/80 outline-none cursor-pointer focus:border-gold/50 transition-colors uppercase tracking-wide"
              >
                <option value="XAUUSD">XAU/USD</option>
                <option value="XAGUSD">XAG/USD</option>
                <option value="BTCUSD">BTC/USD</option>
                <option value="EURUSD">EUR/USD</option>
                <option value="GBPUSD">GBP/USD</option>
              </select>

              {price > 0 && (
                <div className="flex items-center gap-2 ml-1">
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
          <div className="pl-1">
             <SignOutButton />
          </div>
        </div>
      </header>

      {/* Mobile Controls Row (Only visible on small screens) */}
      <div className="flex md:hidden flex-none w-full bg-[#0f1219] px-2 py-1.5 border-b border-white/5 overflow-x-auto hide-scrollbar gap-2">
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
            absolute md:relative z-20 left-0 h-full shrink-0 w-[85vw]
            transition-all duration-300 ease-in-out
            bg-[#0f1219] border-r border-white/5
            ${leftOpen 
              ? "translate-x-0 shadow-[20px_0_40px_rgba(0,0,0,0.5)] md:shadow-none md:w-[300px]" 
              : "-translate-x-full md:translate-x-0 md:w-0 border-r-transparent"}
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
                {!config.apiKey && <p className="text-[10px] font-semibold text-warning mt-2 bg-warning/10 p-2 rounded border border-warning/20">No API key found. System requires LLM key in <Link href="/config" className="underline hover:text-white">Settings</Link>.</p>}
              </div>

              {/* Section: Active Signal */}
              <div>
                <h2 className="text-[9px] font-bold text-white/40 uppercase tracking-widest pl-1 mb-2 block">Actionable Intelligence</h2>
                {displaySignal ? (
                  <SignalCard signal={displaySignal} onExecute={handleExecuteSignal} />
                ) : (
                  <div className="bg-[#131722] rounded-lg border border-white/5 p-6 flex flex-col items-center justify-center text-center">
                    <BarChart3 className="h-6 w-6 text-white/10 mb-3" />
                    <p className="text-[11px] font-medium text-white/40 uppercase tracking-wider">No Valid Setup</p>
                    <p className="text-[10px] text-white/20 mt-1 max-w-[200px]">Engine is crunching {timeframe} candles. Awaiting high probability configuration.</p>
                  </div>
                )}
              </div>
              
              {/* Performance Mini-Dashboard */}
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
              </div>
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
               <History className="h-4 w-4" />
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
                />
              </div>
            )}
          </div>

          {/* ── EXECUTION TERMINAL (BOTTOM PANEL) ── */}
          <div className="h-48 md:h-56 flex-none bg-[#0a0d14] flex flex-col relative z-20">
            <div className="flex items-center justify-between px-3 py-2 border-b border-white/5 bg-[#0f1219]">
              <h2 className="text-[10px] font-bold tracking-widest uppercase text-white/50 flex items-center gap-2">
                <Terminal className="h-3 w-3" /> System Terminal
              </h2>
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse max-md:hidden" />
                <span className="text-[9px] font-(family-name:--font-jetbrains-mono) text-bullish tracking-wider hidden md:inline">SYSTEM.ACTIVE</span>
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto p-2 font-(family-name:--font-jetbrains-mono) text-[10px] space-y-1 hide-scrollbar">
              {displayHistory.slice(0, 15).map((sig) => (
                <div key={`${sig.id || sig.timestamp}-${sig.symbol}`} className="flex items-center gap-3 hover:bg-white/5 p-1 rounded transition-colors group">
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
                <div className="text-white/20 p-2 italic flex items-center justify-center h-full">Waiting for signal execution commands...</div>
              )}
            </div>
          </div>
        </main>

        {/* ── RIGHT PANEL ── */}
        <aside 
          className={`
            absolute md:relative z-20 right-0 h-full shrink-0 w-[85vw]
            transition-all duration-300 ease-in-out
            bg-[#0f1219] border-l border-white/5
            ${rightOpen 
              ? "translate-x-0 shadow-[-20px_0_40px_rgba(0,0,0,0.5)] md:shadow-none md:w-[320px]" 
              : "translate-x-full md:translate-x-0 md:w-0 border-l-transparent"}
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
              {rightTab === "news" && (
                newsLoading
                  ? <div className="space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="h-20 rounded bg-white/5 animate-pulse" />)}</div>
                  : <NewsSentiment items={newsItems} />
              )}
              {rightTab === "calendar" && (
                calendarLoading
                  ? <div className="space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="h-16 rounded bg-white/5 animate-pulse" />)}</div>
                  : <EconomicCalendar events={calendarEvents} />
              )}
              {rightTab === "history" && (
                historyLoading
                  ? <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="h-12 rounded bg-white/5 animate-pulse" />)}</div>
                  : (
                    <>
                      {displayHistory.length > 0 && (
                        <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-2">
                          <span className="text-[9px] font-bold tracking-widest text-white/30 uppercase">{displayHistory.length} Record{displayHistory.length !== 1 ? "s" : ""}</span>
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