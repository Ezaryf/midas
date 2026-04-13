"use client";

import { useState } from "react";
import Link from "next/link";
import {
  TrendingUp, ArrowLeft, Monitor, Brain, Sliders, Shield,
  Eye, EyeOff, CheckCircle2, XCircle, Loader2, Download, Zap, RefreshCw, Layers, Crosshair
} from "lucide-react";
import { useConfig } from "@/hooks/useConfig";
import { useConnectionStatus } from "@/hooks/useConnectionStatus";
import { useMidasStore } from "@/store/useMidasStore";

type Tab = "setup" | "ai" | "trading" | "risk" | "monitor";

const TABS: { id: Tab; label: string; icon: typeof Monitor }[] = [
  { id: "setup",   label: "Setup",    icon: Monitor },
  { id: "ai",      label: "AI Model", icon: Brain   },
  { id: "trading", label: "Trading",  icon: Sliders },
  { id: "risk",    label: "Risk",     icon: Shield  },
  { id: "monitor", label: "Position Mgt", icon: Layers },
];

const AI_PROVIDERS = [
  { id: "openai", label: "OpenAI",    model: "GPT-4o",        hint: "Best quality" },
  { id: "groq",   label: "Groq",      model: "Llama 3.3 70B", hint: "Fastest - Free tier" },
  { id: "claude", label: "Anthropic", model: "Claude Sonnet", hint: "Great reasoning" },
  { id: "gemini", label: "Google",    model: "Gemini Flash",  hint: "Multimodal" },
  { id: "grok",   label: "xAI",       model: "Grok 3",        hint: "Real-time data" },
];

const TRADING_STYLES = [
  { id: "scalper",  label: "Scalper",  desc: "1-5 min holds",  tf: "M1, M3, M5",  risk: "0.5%" },
  { id: "intraday", label: "Intraday", desc: "Same-day trades", tf: "M15, H1, H4", risk: "1.0%" },
  { id: "swing",    label: "Swing",    desc: "Multi-day holds", tf: "H4, D1, W1",  risk: "2.0%" },
];

export default function ConfigPage() {
  const { config, save, loaded } = useConfig();
  const { state: connState, checkBackend } = useConnectionStatus();
  const isWsConnected = useMidasStore(s => s.isConnected);

  const [tab, setTab]         = useState<Tab>("setup");
  const [showPw, setShowPw]   = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);

  const [mt5State, setMt5State] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [mt5Info, setMt5Info]   = useState<Record<string, unknown> | null>(null);
  const [mt5Err, setMt5Err]     = useState("");
  const [aiState, setAiState]   = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [aiMsg, setAiMsg]       = useState("");

  // Once config loads from localStorage, restore connection indicators
  if (loaded && mt5State === "idle" && config.mt5Account && config.mt5Server) {
    setMt5State("ok");
  }
  if (loaded && aiState === "idle" && config.apiKey) {
    setAiState("ok");
    setAiMsg("Saved (" + config.aiProvider + ")");
  }

  if (!loaded) return null;

  const flash = () => { setSavedFlash(true); setTimeout(() => setSavedFlash(false), 1500); };

  const saveField = (key: keyof typeof config, value: string | number | boolean) => {
    save({ [key]: value });
    flash();
  };

  const syncSettingToBackend = async (key: string, value: number | boolean) => {
    try {
      const body: Record<string, number | boolean> = {};
      if (key === "maxConcurrentPositions") body.max_concurrent_positions = value;
      else if (key === "maxDailyTrades") body.max_daily_trades = value;
      else if (key === "dailyLossLimit") body.daily_loss_limit = value;
      else if (key === "maxRiskPercent") body.max_risk_percent = value;
      else if (key === "newsBlackoutMinutes") body.news_blackout_minutes = value;
      else if (key === "autoExecuteConfidence") body.auto_execute_confidence = value;
      else if (key === "analysisIntervalSeconds") body.analysis_interval_seconds = value;
      else if (key === "positionCooldownSeconds") body.position_cooldown_seconds = value;
      else if (key === "enableKillSwitch") body.enable_kill_switch = value;
      else if (key === "minLotSize") body.min_lot_size = value;
      else if (key === "maxLotSize") body.max_lot_size = value;
      else if (key === "minStopDistancePoints") body.min_stop_distance_points = value;
      else if (key === "partialCloseEnabled") body.partial_close_enabled = value;
      else if (key === "partialClosePercent") body.partial_close_percent = value;
      else if (key === "breakevenEnabled") body.breakeven_enabled = value;
      else if (key === "breakevenBufferPips") body.breakeven_buffer_pips = value;
      else if (key === "trailingStopEnabled") body.trailing_stop_enabled = value;
      else if (key === "trailingStopDistancePips") body.trailing_stop_distance_pips = value;
      else if (key === "trailingStopStepPips") body.trailing_stop_step_pips = value;
      else if (key === "timeExitEnabled") body.time_exit_enabled = value;
      else if (key === "exitBeforeNewsMinutes") body.exit_before_news_minutes = value;
      else if (key === "exitBeforeWeekendHours") body.exit_before_weekend_hours = value;
      
      if (Object.keys(body).length > 0) {
        await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      }
    } catch { /* backend may be offline */ }
  };

  const saveRiskField = (key: keyof typeof config, value: number) => {
    saveField(key, value);
    syncSettingToBackend(key, value);
  };

  const testMt5 = async () => {
    if (!config.mt5Account || !config.mt5Password || !config.mt5Server) {
      setMt5State("error"); setMt5Err("Fill all three fields first."); return;
    }
    if (mt5State === "ok") {
      setMt5State("idle");
    }
    setMt5State("testing"); setMt5Info(null); setMt5Err("");
    try {
      const res = await fetch("/api/mt5/validate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: parseInt(config.mt5Account), password: config.mt5Password, server: config.mt5Server, symbol: "GOLD" }),
        signal: AbortSignal.timeout(20_000),
      });
      const d = await res.json();
      if (d.status === "ok") {
        setMt5State("ok"); setMt5Info(d);
        save({ mt5Account: config.mt5Account, mt5Server: config.mt5Server, mt5Password: config.mt5Password });
        flash();
      } else { setMt5State("error"); setMt5Err(d.message ?? "Failed"); }
    } catch { setMt5State("error"); setMt5Err("Backend offline — start the server first."); }
  };

  const testAi = async () => {
    if (!config.apiKey) { setAiState("error"); setAiMsg("Enter an API key first."); return; }
    setAiState("testing"); setAiMsg("");
    try {
      const res = await fetch("/api/ai/validate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ api_key: config.apiKey, ai_provider: config.aiProvider }),
      });
      const d = await res.json();
      if (d.status === "ok") {
        setAiState("ok"); setAiMsg("Connected — " + d.model);
        save({ apiKey: config.apiKey, aiProvider: config.aiProvider }); flash();
      } else { setAiState("error"); setAiMsg(d.message ?? "Invalid key"); }
    } catch { setAiState("error"); setAiMsg("Request failed"); }
  };

  const downloadEnv = () => {
    const lines = [
      "# Midas Backend Configuration",
      "MT5_LOGIN=" + config.mt5Account, "MT5_PASSWORD=<ENTER_YOUR_PASSWORD>",
      "MT5_SERVER=" + config.mt5Server, "MT5_SYMBOL=GOLD",
      "MIDAS_WS_URL=ws://localhost:8000/ws/mt5", "DEFAULT_LOT=0.01", "TICK_INTERVAL=0.1",
      "AI_PROVIDER=" + config.aiProvider, "AI_API_KEY=<ENTER_YOUR_API_KEY>",
      "TRADING_STYLE=" + (config.tradingStyle.charAt(0).toUpperCase() + config.tradingStyle.slice(1)),
      "ANALYSIS_INTERVAL_SECONDS=" + config.analysisIntervalSeconds,
      "AUTO_EXECUTE_MIN_CONFIDENCE=" + config.autoExecuteConfidence,
      "MAX_DAILY_TRADES=" + config.maxDailyTrades,
      "MAX_CONCURRENT_POSITIONS=" + config.maxConcurrentPositions,
      "MAX_RISK_PERCENT=" + config.maxRiskPercent,
      "MIN_LOT_SIZE=" + config.minLotSize,
      "MAX_LOT_SIZE=" + config.maxLotSize,
      "MIN_STOP_DISTANCE_POINTS=" + config.minStopDistancePoints,
      "DAILY_LOSS_LIMIT=" + config.dailyLossLimit,
      "NEWS_BLACKOUT_MINUTES=" + config.newsBlackoutMinutes,
      "POSITION_COOLDOWN_SECONDS=" + config.positionCooldownSeconds,
      "PARTIAL_CLOSE_ENABLED=" + config.partialCloseEnabled,
      "PARTIAL_CLOSE_PERCENT=" + config.partialClosePercent,
      "BREAKEVEN_ENABLED=" + config.breakevenEnabled,
      "BREAKEVEN_BUFFER_PIPS=" + config.breakevenBufferPips,
      "TRAILING_STOP_ENABLED=" + config.trailingStopEnabled,
      "TRAILING_STOP_DISTANCE_PIPS=" + config.trailingStopDistancePips,
      "TRAILING_STOP_STEP_PIPS=" + config.trailingStopStepPips,
      "TIME_EXIT_ENABLED=" + config.timeExitEnabled,
      "EXIT_BEFORE_NEWS_MINUTES=" + config.exitBeforeNewsMinutes,
      "EXIT_BEFORE_WEEKEND_HOURS=" + config.exitBeforeWeekendHours,
    ].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines], { type: "text/plain" }));
    a.download = ".env"; a.click();
  };

  const backendOk = connState.backend === "connected";
  const mt5Ok     = isWsConnected || mt5State === "ok";
  const ic = "w-full rounded-xl bg-surface border border-border px-4 py-2.5 text-sm placeholder:text-text-muted focus:outline-none focus:border-gold/40 focus:ring-1 focus:ring-gold/20 transition-all";

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border px-4 py-3 shrink-0">
        <div className="flex items-center justify-between max-w-3xl mx-auto">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors">
              <ArrowLeft className="h-3.5 w-3.5" />Dashboard
            </Link>
            <div className="h-4 w-px bg-border" />
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gold/10 border border-gold/20">
                <TrendingUp className="h-3.5 w-3.5 text-gold" />
              </div>
              <span className="text-sm font-semibold">Settings</span>
            </div>
          </div>
          {savedFlash && <span className="text-xs text-bullish flex items-center gap-1"><CheckCircle2 className="h-3 w-3" />Saved</span>}
        </div>
      </header>

      <div className="flex flex-1 max-w-3xl mx-auto w-full">
        <nav className="w-40 shrink-0 border-r border-border p-3 space-y-1">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={"w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-xs font-medium transition-all text-left " +
                (tab === t.id ? "bg-gold/10 text-gold border border-gold/20" : "text-text-muted hover:text-text-secondary hover:bg-surface")}>
              <t.icon className="h-3.5 w-3.5 shrink-0" />{t.label}
            </button>
          ))}
          <div className="pt-4 space-y-2 border-t border-border mt-4">
            {[
              { ok: backendOk,        label: backendOk        ? "Backend"  : "No backend"  },
              { ok: mt5Ok,            label: mt5Ok            ? "MT5 live" : "MT5 offline"  },
              { ok: aiState === "ok", label: aiState === "ok" ? config.aiProvider : "No AI key" },
            ].map(({ ok, label }) => (
              <div key={label} className="flex items-center gap-1.5 px-3">
                <span className={"h-1.5 w-1.5 rounded-full shrink-0 " + (ok ? "bg-bullish animate-pulse" : "bg-text-muted")} />
                <span className="text-xs text-text-muted truncate">{label}</span>
              </div>
            ))}
          </div>
        </nav>

        <main className="flex-1 p-6 overflow-y-auto">
          {tab === "setup" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold mb-0.5">MT5 Account</h2>
                <p className="text-xs text-text-muted">Credentials are saved to your browser and restored automatically.</p>
              </div>
              {mt5State === "ok" && mt5Info && (
                <div className="rounded-xl bg-bullish/5 border border-bullish/20 p-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {[
                    { label: "Name",     value: String(mt5Info.name) },
                    { label: "Balance",  value: mt5Info.balance + " " + mt5Info.currency, color: "text-bullish" },
                    { label: "Leverage", value: "1:" + mt5Info.leverage },
                    { label: "Price",    value: mt5Info.bid ? mt5Info.bid + "/" + mt5Info.ask : "-", color: "text-gold" },
                  ].map(({ label, value, color }) => (
                    <div key={label}>
                      <span className="text-xs text-text-muted">{label}</span>
                      <p className={"text-sm font-bold font-[family-name:var(--font-jetbrains-mono)] " + (color ?? "")}>{value}</p>
                    </div>
                  ))}
                </div>
              )}
              {mt5State === "ok" && !mt5Info && config.mt5Account && (
                <div className="rounded-xl bg-surface border border-border p-3 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 text-bullish shrink-0" />
                  <span className="text-xs text-text-secondary">Saved: Account {config.mt5Account} on {config.mt5Server}</span>
                </div>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">Account Number</label>
                  <input value={config.mt5Account}
                    onChange={e => { saveField("mt5Account", e.target.value); setMt5State("idle"); }}
                    placeholder="316798303" className={ic + " font-[family-name:var(--font-jetbrains-mono)]"} />
                </div>
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">Server</label>
                  <input value={config.mt5Server}
                    onChange={e => { saveField("mt5Server", e.target.value); setMt5State("idle"); }}
                    placeholder="XMGlobal-MT5 7" className={ic} />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-text-secondary mb-1.5">Password</label>
                  <div className="relative">
                    <input type={showPw ? "text" : "password"} value={config.mt5Password}
                      onChange={e => { saveField("mt5Password", e.target.value); setMt5State("idle"); }}
                      placeholder="Your MT5 password" className={ic + " pr-10"} />
                    <button type="button" onClick={() => setShowPw(!showPw)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary">
                      {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                  <p className="mt-1 text-xs text-text-muted">Saved in browser storage — persists across sessions.</p>
                </div>
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                <button onClick={testMt5}
                  disabled={mt5State === "testing"}
                  className={"flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all disabled:opacity-50 " +
                    (mt5State === "ok" ? "bg-bullish/10 border border-bullish/20 text-bullish" : mt5State === "error" ? "bg-bearish/10 border border-bearish/20 text-bearish" : "bg-gradient-to-r from-gold-dark via-gold to-gold-light text-background hover:shadow-lg hover:shadow-gold/20")}>
                  {mt5State === "testing" ? <><Loader2 className="h-4 w-4 animate-spin" />Connecting...</>
                    : mt5State === "ok"   ? <><CheckCircle2 className="h-4 w-4" />Connected</>
                    : mt5State === "error" ? <><XCircle className="h-4 w-4" />Retry</>
                    : <><Monitor className="h-4 w-4" />Connect MT5</>}
                </button>
                {mt5State !== "ok" && mt5State !== "testing" && (!config.mt5Account || !config.mt5Server) && (
                  <span className="text-xs text-text-muted">Fill account & server to connect</span>
                )}
                {mt5State === "ok" && (
                  <button onClick={downloadEnv}
                    className="flex items-center gap-2 rounded-xl bg-surface border border-border px-4 py-2.5 text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-all">
                    <Download className="h-4 w-4" />Download .env
                  </button>
                )}
                {mt5State === "error" && <span className="flex items-center gap-1.5 text-xs text-bearish"><XCircle className="h-3.5 w-3.5" />{mt5Err}</span>}
              </div>
              <div className="flex items-center justify-between rounded-xl bg-surface p-4">
                <div>
                  <p className="text-sm font-medium">Auto-Trade Mode</p>
                  <p className="text-xs text-text-muted">{config.autoTrade ? "Orders execute automatically when signals fire" : "Manual execution only"}</p>
                </div>
                <button onClick={() => saveField("autoTrade", !config.autoTrade)}
                  className={"relative h-6 w-11 rounded-full transition-colors " + (config.autoTrade ? "bg-bullish" : "bg-surface-active")}>
                  <span className={"absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform " + (config.autoTrade ? "translate-x-5" : "")} />
                </button>
              </div>
              <div className="rounded-xl bg-surface/50 border border-border p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={"h-2 w-2 rounded-full " + (backendOk ? "bg-bullish animate-pulse" : "bg-text-muted")} />
                    <span className="text-xs font-medium">{backendOk ? "Python backend online" : "Python backend offline"}</span>
                  </div>
                  <button onClick={checkBackend} className="text-text-muted hover:text-text-secondary"><RefreshCw className="h-3.5 w-3.5" /></button>
                </div>
                {!backendOk && <p className="mt-2 text-xs text-text-muted font-[family-name:var(--font-jetbrains-mono)]">cd backend &amp;&amp; uvicorn main:app --reload</p>}
              </div>
            </div>
          )}

          {tab === "ai" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold mb-0.5">AI Model</h2>
                <p className="text-xs text-text-muted">Pick a provider and paste your API key. Groq is free and fastest.</p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {AI_PROVIDERS.map(p => (
                  <button key={p.id}
                    onClick={() => { saveField("aiProvider", p.id as typeof config.aiProvider); setAiState("idle"); }}
                    className={"rounded-xl p-3 text-left transition-all " +
                      (config.aiProvider === p.id ? "bg-info/10 border-2 border-info/30" : "bg-surface border-2 border-transparent hover:border-border")}>
                    <div className="flex items-center justify-between mb-1">
                      <p className="text-sm font-semibold">{p.label}</p>
                      {config.aiProvider === p.id && <CheckCircle2 className="h-3.5 w-3.5 text-info" />}
                    </div>
                    <p className="text-xs text-text-muted">{p.model}</p>
                    <p className="text-xs text-info/70 mt-1">{p.hint}</p>
                  </button>
                ))}
              </div>
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1.5">
                  API Key ({AI_PROVIDERS.find(p => p.id === config.aiProvider)?.label})
                </label>
                <div className="relative">
                  <input type={showKey ? "text" : "password"} value={config.apiKey}
                    onChange={e => { saveField("apiKey", e.target.value); setAiState("idle"); }}
                    placeholder="Paste your API key here"
                    className={ic + " pr-10 font-[family-name:var(--font-jetbrains-mono)]"} />
                  <button type="button" onClick={() => setShowKey(!showKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary">
                    {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="mt-1 text-xs text-text-muted">Saved automatically as you type.</p>
              </div>
              <div className="flex items-center gap-3">
                <button onClick={testAi} disabled={aiState === "testing" || !config.apiKey}
                  className="flex items-center gap-2 rounded-xl bg-info/10 border border-info/20 px-5 py-2.5 text-sm font-medium text-info hover:bg-info/20 transition-all disabled:opacity-50 disabled:pointer-events-none">
                  {aiState === "testing" ? <><Loader2 className="h-4 w-4 animate-spin" />Testing...</>
                    : aiState === "ok"   ? <><CheckCircle2 className="h-4 w-4" />Connected</>
                    : <><Zap className="h-4 w-4" />Test Connection</>}
                </button>
                {aiState === "ok"    && <span className="text-xs text-bullish">{aiMsg}</span>}
                {aiState === "error" && <span className="flex items-center gap-1 text-xs text-bearish"><XCircle className="h-3.5 w-3.5" />{aiMsg}</span>}
              </div>
              <div className="rounded-xl bg-surface/50 border border-border p-4 text-xs text-text-muted space-y-1.5">
                <p className="font-medium text-text-secondary mb-2">Where to get keys:</p>
                {[["OpenAI","platform.openai.com"],["Groq (free)","console.groq.com"],["Anthropic","console.anthropic.com"],["Google","aistudio.google.com"],["xAI","console.x.ai"]].map(([n,u]) => (
                  <p key={u}>{n} <span className="text-gold">{u}</span></p>
                ))}
              </div>
            </div>
          )}

          {tab === "trading" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold mb-0.5">Trading Style</h2>
                <p className="text-xs text-text-muted">Tailors signal frequency, execution thresholds, and loop behavior. Saved immediately.</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {TRADING_STYLES.map(s => (
                  <button key={s.id} onClick={() => saveField("tradingStyle", s.id as typeof config.tradingStyle)}
                    className={"rounded-xl p-4 text-left transition-all " +
                      (config.tradingStyle === s.id ? "bg-gold/10 border-2 border-gold/30" : "bg-surface border-2 border-transparent hover:border-border")}>
                    <div className="flex items-center justify-between mb-1">
                      <p className="text-sm font-semibold">{s.label}</p>
                      {config.tradingStyle === s.id && <CheckCircle2 className="h-3.5 w-3.5 text-gold" />}
                    </div>
                    <p className="text-xs text-text-muted mb-3">{s.desc}</p>
                    <p className="text-xs text-text-muted">TF: {s.tf}</p>
                    <p className="text-xs text-text-muted">Risk: {s.risk}</p>
                  </button>
                ))}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {([
                  { key: "autoExecuteConfidence", label: "Auto-Execute Confidence", unit: "%", step: 1, min: 50, max: 99 },
                  { key: "maxDailyTrades", label: "Max Daily Trades", unit: "trades", step: 1, min: 1, max: 1000 },
                  { key: "analysisIntervalSeconds", label: "Analysis Interval", unit: "sec", step: 1, min: 3, max: 300 },
                  { key: "positionCooldownSeconds", label: "Signal Cooldown", unit: "sec", step: 5, min: 0, max: 300 },
                ] as const).map(({ key, label, unit, step, min, max }) => (
                  <div key={key} className="rounded-xl bg-surface p-4">
                    <div className="flex items-center justify-between mb-3">
                      <label className="text-xs font-medium text-text-secondary">{label}</label>
                      <span className="text-xs text-text-muted">{unit}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min={min}
                        max={max}
                        step={step}
                        value={(config as unknown as Record<string, number>)[key]}
                        onChange={e => saveRiskField(key as keyof typeof config, parseFloat(e.target.value))}
                        className="flex-1 accent-gold"
                      />
                      <input
                        type="number"
                        min={min}
                        max={max}
                        step={step}
                        value={(config as unknown as Record<string, number>)[key]}
                        onChange={e => saveRiskField(key as keyof typeof config, parseFloat(e.target.value))}
                        className="w-20 rounded-lg bg-surface-active border border-border px-2 py-1.5 text-sm text-center font-[family-name:var(--font-jetbrains-mono)] focus:outline-none focus:border-gold/40"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === "risk" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold mb-0.5">Risk Management</h2>
                <p className="text-xs text-text-muted">Hard limits to protect your capital. Saved immediately.</p>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {([
                  { key: "maxRiskPercent",      label: "Max Risk Per Trade", unit: "%",       step: 0.1, min: 0.1, max: 100  },
                  { key: "dailyLossLimit",      label: "Daily Loss Limit",   unit: "$",       step: 50,  min: 0,   max: 100000 },
                  { key: "newsBlackoutMinutes", label: "News Blackout",      unit: "min",     step: 5,   min: 0,   max: 120   },
                  { key: "maxConcurrentPositions", label: "Max Concurrent Positions",  unit: "trades",  step: 1,   min: 1,   max: 100   },
                ] as const).map(({ key, label, unit, step, min, max }) => (
                  <div key={key} className="rounded-xl bg-surface p-4">
                    <div className="flex items-center justify-between mb-3">
                      <label className="text-xs font-medium text-text-secondary">{label}</label>
                      <span className="text-xs text-text-muted">{unit}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <input type="range" min={min} max={max} step={step}
                        value={(config as unknown as Record<string, number>)[key]}
                        onChange={e => saveRiskField(key as keyof typeof config, parseFloat(e.target.value))}
                        className="flex-1 accent-gold" />
                      <input type="number" min={min} max={max} step={step}
                        value={(config as unknown as Record<string, number>)[key]}
                        onChange={e => saveRiskField(key as keyof typeof config, parseFloat(e.target.value))}
                        className="w-20 rounded-lg bg-surface-active border border-border px-2 py-1.5 text-sm text-center font-[family-name:var(--font-jetbrains-mono)] focus:outline-none focus:border-gold/40" />
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between rounded-xl bg-surface p-4">
                <div>
                  <p className="text-sm font-medium">Kill Switch</p>
                  <p className="text-xs text-text-muted">{config.enableKillSwitch ? "Halts trading on stale data, drawdown, or losing streaks" : "Kill switch disabled — no automatic trading halt"}</p>
                </div>
                <button onClick={() => { saveField("enableKillSwitch", !config.enableKillSwitch); syncSettingToBackend("enableKillSwitch", !config.enableKillSwitch); }}
                  className={"relative h-6 w-11 rounded-full transition-colors " + (config.enableKillSwitch ? "bg-bullish" : "bg-surface-active")}>
                  <span className={"absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform " + (config.enableKillSwitch ? "translate-x-5" : "")} />
                </button>
              </div>
              <div className="rounded-xl bg-warning/5 border border-warning/20 p-4">
                <p className="text-xs text-warning">AI signals are not financial advice. Only trade capital you can afford to lose.</p>
              </div>
            </div>
          )}

          {tab === "monitor" && (
            <div className="space-y-6">
              <div>
                <h2 className="text-base font-semibold mb-0.5">Position Management</h2>
                <p className="text-xs text-text-muted">Dynamic rules for managing active trades and locking in profits.</p>
              </div>
              
              <div className="space-y-4">
                {([
                  { key: "partialCloseEnabled", label: "Partial Close at TP1", desc: "Close a percentage of the position at the first take profit level." },
                  { key: "breakevenEnabled", label: "Move to Break-Even", desc: "Move stop loss to entry price + buffer after partial close." },
                  { key: "trailingStopEnabled", label: "Trailing Stop", desc: "Automatically trail the stop loss to protect profits." },
                  { key: "timeExitEnabled", label: "Time-Based Exits", desc: "Close positions automatically before news or weekends." },
                ] as const).map(({ key, label, desc }) => (
                  <div key={key} className="flex items-center justify-between rounded-xl bg-surface p-4">
                    <div>
                      <p className="text-sm font-medium">{label}</p>
                      <p className="text-xs text-text-muted">{desc}</p>
                    </div>
                    <button onClick={() => { 
                        const newBool = !(config as unknown as Record<string, boolean>)[key];
                        saveField(key as keyof typeof config, newBool); 
                        syncSettingToBackend(key, newBool); 
                      }}
                      className={"relative h-6 w-11 shrink-0 rounded-full transition-colors " + ((config as unknown as Record<string, boolean>)[key] ? "bg-bullish" : "bg-surface-active")}>
                      <span className={"absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform " + ((config as unknown as Record<string, boolean>)[key] ? "translate-x-5" : "")} />
                    </button>
                  </div>
                ))}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                {([
                  { key: "partialClosePercent", label: "Partial Close", unit: "%", step: 5, min: 10, max: 90, showIf: config.partialCloseEnabled },
                  { key: "breakevenBufferPips", label: "Break-Even Buffer", unit: "pips", step: 1, min: 0, max: 20, showIf: config.breakevenEnabled },
                  { key: "trailingStopDistancePips", label: "Trailing Distance", unit: "pips", step: 5, min: 10, max: 200, showIf: config.trailingStopEnabled },
                  { key: "trailingStopStepPips", label: "Trailing Step", unit: "pips", step: 1, min: 1, max: 50, showIf: config.trailingStopEnabled },
                  { key: "exitBeforeNewsMinutes", label: "News Exit Buffer", unit: "min", step: 5, min: 5, max: 120, showIf: config.timeExitEnabled },
                  { key: "exitBeforeWeekendHours", label: "Weekend Exit Buffer", unit: "hrs", step: 1, min: 1, max: 48, showIf: config.timeExitEnabled },
                ] as const).filter(i => i.showIf).map(({ key, label, unit, step, min, max }) => (
                  <div key={key} className="rounded-xl bg-surface p-4 border-l-2 border-gold/50">
                    <div className="flex items-center justify-between mb-3">
                      <label className="text-xs font-medium text-text-secondary">{label}</label>
                      <span className="text-xs text-text-muted">{unit}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <input type="range" min={min} max={max} step={step}
                        value={(config as unknown as Record<string, number>)[key]}
                        onChange={e => saveRiskField(key as keyof typeof config, parseFloat(e.target.value))}
                        className="flex-1 accent-gold" />
                      <input type="number" min={min} max={max} step={step}
                        value={(config as unknown as Record<string, number>)[key]}
                        onChange={e => saveRiskField(key as keyof typeof config, parseFloat(e.target.value))}
                        className="w-20 rounded-lg bg-surface-active border border-border px-2 py-1.5 text-sm text-center font-[family-name:var(--font-jetbrains-mono)] focus:outline-none focus:border-gold/40" />
                    </div>
                  </div>
                ))}
              </div>
              
              <div className="grid gap-4 sm:grid-cols-3">
                {([
                  { key: "minLotSize", label: "Min Lot", unit: "lots", step: 0.01, min: 0.01, max: 10 },
                  { key: "maxLotSize", label: "Max Lot", unit: "lots", step: 0.01, min: 0.01, max: 100 },
                  { key: "minStopDistancePoints", label: "Min Stop Dist", unit: "pts", step: 10, min: 10, max: 500 },
                ] as const).map(({ key, label, unit, step, min, max }) => (
                  <div key={key} className="rounded-xl bg-surface p-4">
                    <div className="flex items-center justify-between mb-3">
                      <label className="text-xs font-medium text-text-secondary">{label}</label>
                    </div>
                    <div className="flex items-center gap-2">
                       <input type="number" min={min} max={max} step={step}
                        value={(config as unknown as Record<string, number>)[key]}
                        onChange={e => saveRiskField(key as keyof typeof config, parseFloat(e.target.value))}
                        className="w-full rounded-lg bg-surface-active border border-border px-2 py-1.5 text-sm text-center font-[family-name:var(--font-jetbrains-mono)] focus:outline-none focus:border-gold/40" />
                       <span className="text-xs text-text-muted w-8">{unit}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
