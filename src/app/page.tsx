import Link from "next/link";
import {
  TrendingUp,
  Brain,
  Zap,
  BarChart3,
  Shield,
  Newspaper,
  ArrowRight,
  Activity,
  Target,
  LineChart,
} from "lucide-react";
import LivePriceTicker from "@/components/data/LivePriceTicker";

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Background Effects */}
      <div className="fixed inset-0 bg-gradient-radial-gold pointer-events-none" />
      <div className="fixed inset-0 bg-grid opacity-40 pointer-events-none" />

      {/* Navigation */}
      <nav className="relative z-10 flex items-center justify-between px-6 py-4 lg:px-12">
        <Link href="/" className="flex items-center gap-2 group">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gold/10 border border-gold/20 group-hover:bg-gold/20 transition-colors">
            <TrendingUp className="h-5 w-5 text-gold" />
          </div>
          <span className="text-xl font-bold tracking-tight font-[family-name:var(--font-space-grotesk)]">
            <span className="text-gradient-gold">Midas</span>
          </span>
        </Link>
        <div className="flex items-center gap-4">
          <Link
            href="/login"
            className="text-sm text-text-secondary hover:text-text-primary transition-colors"
          >
            Sign In
          </Link>
          <Link
            href="/dashboard"
            className="group flex items-center gap-2 rounded-lg bg-gold/10 border border-gold/20 px-4 py-2 text-sm font-medium text-gold hover:bg-gold/20 transition-all"
          >
            Go to Dashboard
            <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative z-10 flex flex-col items-center justify-center px-6 pt-20 pb-24 text-center lg:pt-32 lg:pb-32">
        {/* Badge */}
        <div className="animate-fade-in mb-8">
          <div className="glass-gold inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium text-gold">
            <Activity className="h-3 w-3" />
            <span>AI-Powered Gold Trading</span>
            <span className="h-1.5 w-1.5 rounded-full bg-bullish animate-pulse" />
          </div>
        </div>

        {/* Main Heading */}
        <h1
          className="animate-fade-in-up max-w-4xl text-5xl font-extrabold leading-[1.08] tracking-tight sm:text-6xl lg:text-7xl"
          style={{ animationDelay: "100ms" }}
        >
          Trade Gold with{" "}
          <span className="text-gradient-gold">AI Precision</span>
        </h1>

        {/* Subheading */}
        <p
          className="animate-fade-in-up mt-6 max-w-2xl text-lg text-text-secondary leading-relaxed sm:text-xl"
          style={{ animationDelay: "200ms" }}
        >
          Midas combines real-time technical analysis, news sentiment, and
          economic calendar data to deliver high-confidence XAU/USD trade
          signals — with one-click MT5 execution.
        </p>

        {/* CTA Buttons */}
        <div
          className="animate-fade-in-up mt-10 flex flex-col gap-4 sm:flex-row"
          style={{ animationDelay: "300ms" }}
        >
          <Link
            href="/dashboard"
            className="group relative inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-gold-dark via-gold to-gold-light px-8 py-3.5 text-sm font-semibold text-background shadow-lg shadow-gold/20 hover:shadow-gold/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <Target className="h-4 w-4" />
            Go to Dashboard
            <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
          <a
            href="#how-it-works"
            className="inline-flex items-center justify-center gap-2 rounded-xl glass px-8 py-3.5 text-sm font-medium text-text-primary hover:bg-surface-hover transition-all"
          >
            Learn How It Works
          </a>
        </div>

        <LivePriceTicker />
      </section>

      {/* Benefits Grid */}
      <section className="relative z-10 px-6 pb-24 lg:px-12">
        <div className="mx-auto max-w-6xl">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger-children">
            {[
              {
                icon: Brain,
                title: "AI-Powered Signals",
                desc: "Multi-model LLM analysis fusing technicals, sentiment, and macro data into precise entry/SL/TP levels with confidence scores.",
              },
              {
                icon: Newspaper,
                title: "News-Aware Intelligence",
                desc: "Real-time parsing of economic calendars and news feeds. Auto-adjusts signals around high-impact events like NFP and FOMC.",
              },
              {
                icon: Zap,
                title: "MT5 Auto-Execution",
                desc: "One-click automated order placement on your MetaTrader 5 account with SL/TP attached. Manual fallback always available.",
              },
              {
                icon: BarChart3,
                title: "Visual Chart Annotations",
                desc: "Entry, stop-loss, and take-profit lines drawn directly on interactive TradingView charts. See your trade setup at a glance.",
              },
              {
                icon: Shield,
                title: "Risk Management",
                desc: "Configurable max risk per trade, daily loss limits, and news blackout periods. Your capital is protected by design.",
              },
              {
                icon: LineChart,
                title: "Adaptive Trading Styles",
                desc: "Choose Intraday, Swing, or Scalper — the AI tailors signal frequency, timeframe, and risk parameters to your preference.",
              },
            ].map((item) => (
              <div
                key={item.title}
                className="group glass rounded-2xl p-6 hover:bg-surface-hover transition-all duration-300 hover:-translate-y-0.5"
              >
                <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-gold/8 border border-gold/12 group-hover:bg-gold/15 transition-colors">
                  <item.icon className="h-5 w-5 text-gold" />
                </div>
                <h3 className="text-base font-semibold mb-2">{item.title}</h3>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section
        id="how-it-works"
        className="relative z-10 px-6 pb-24 lg:px-12"
      >
        <div className="mx-auto max-w-4xl text-center">
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl mb-4">
            How <span className="text-gradient-gold">Midas</span> Works
          </h2>
          <p className="text-text-secondary mb-16 max-w-2xl mx-auto">
            From data aggregation to trade execution in three intelligent
            steps.
          </p>

          <div className="grid gap-8 sm:grid-cols-3 stagger-children">
            {[
              {
                step: "01",
                title: "Analyze",
                desc: "Aggregates real-time XAU/USD prices, detects chart patterns, calculates indicators, and scrapes economic calendar + news sentiment.",
              },
              {
                step: "02",
                title: "Reason",
                desc: "Your chosen AI model fuses all data points with your trading style to generate a specific trade signal with entry, SL, TP, and confidence score.",
              },
              {
                step: "03",
                title: "Execute",
                desc: "Auto-places the order on your MT5 account with risk parameters attached — or displays a manual card with one-click copy. You stay in control.",
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl glass-gold">
                  <span className="text-xl font-bold text-gradient-gold font-[family-name:var(--font-jetbrains-mono)]">
                    {item.step}
                  </span>
                </div>
                <h3 className="text-lg font-semibold mb-2">{item.title}</h3>
                <p className="text-sm text-text-secondary leading-relaxed">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="relative z-10 px-6 pb-32 lg:px-12">
        <div className="mx-auto max-w-3xl text-center">
          <div className="glass-gold rounded-3xl p-10 sm:p-14">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl mb-4">
              Ready to trade with{" "}
              <span className="text-gradient-gold">AI edge</span>?
            </h2>
            <p className="text-text-secondary mb-8 max-w-xl mx-auto">
              Connect your MT5 account, choose your AI model, and let Midas
              find high-probability gold setups for you.
            </p>
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-gold-dark via-gold to-gold-light px-8 py-3.5 text-sm font-semibold text-background shadow-lg shadow-gold/20 hover:shadow-gold/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
            >
              <Target className="h-4 w-4" />
              Launch Dashboard
              <ArrowRight className="h-4 w-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-border px-6 py-8 lg:px-12">
        <div className="mx-auto max-w-6xl flex flex-col items-center justify-between gap-4 sm:flex-row">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-gold" />
            <span className="text-sm font-medium text-gradient-gold font-[family-name:var(--font-space-grotesk)]">
              Midas
            </span>
          </div>
          <p className="text-xs text-text-muted text-center sm:text-right max-w-md">
            ⚠️ Not financial advice. Trading involves significant risk of loss.
            Past AI performance does not guarantee future results. Trade
            responsibly.
          </p>
        </div>
      </footer>
    </div>
  );
}
