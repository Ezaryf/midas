"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type Time,
  ColorType,
  CrosshairMode,
  LineStyle,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
} from "lightweight-charts";

export interface ChartLine {
  price: number;
  color: string;
  label: string;
  style?: LineStyle;
}

interface OHLCVData extends CandlestickData<Time> {
  volume?: number;
}

interface TradingViewChartProps {
  data: OHLCVData[];
  lines?: ChartLine[];
  height?: number;
}

// ── EMA calculation ───────────────────────────────────────────────────────────
function calcEMA(data: OHLCVData[], period: number): { time: Time; value: number }[] {
  const k = 2 / (period + 1);
  const result: { time: Time; value: number }[] = [];
  let ema = 0;
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) continue;
    if (i === period - 1) {
      ema = data.slice(0, period).reduce((s, c) => s + c.close, 0) / period;
    } else {
      ema = data[i].close * k + ema * (1 - k);
    }
    result.push({ time: data[i].time, value: Number.parseFloat(ema.toFixed(2)) });
  }
  return result;
}

// ── RSI calculation ───────────────────────────────────────────────────────────
function calcRSI(data: OHLCVData[], period = 14): { time: Time; value: number }[] {
  const result: { time: Time; value: number }[] = [];
  if (data.length < period + 1) return result;

  let avgGain = 0, avgLoss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = data[i].close - data[i - 1].close;
    if (diff > 0) avgGain += diff; else avgLoss += Math.abs(diff);
  }
  avgGain /= period;
  avgLoss /= period;

  for (let i = period; i < data.length; i++) {
    if (i > period) {
      const diff = data[i].close - data[i - 1].close;
      avgGain = (avgGain * (period - 1) + Math.max(diff, 0)) / period;
      avgLoss = (avgLoss * (period - 1) + Math.max(-diff, 0)) / period;
    }
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    result.push({ time: data[i].time, value: Number.parseFloat((100 - 100 / (1 + rs)).toFixed(2)) });
  }
  return result;
}

// ── Tooltip state ─────────────────────────────────────────────────────────────
interface TooltipData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  change: number;
  changePct: number;
  x: number;
  y: number;
  containerWidth: number;
  visible: boolean;
}

export default function TradingViewChart({ data, lines = [], height = 500 }: TradingViewChartProps) {
  const containerRef  = useRef<HTMLDivElement>(null);
  const chartRef      = useRef<IChartApi | null>(null);
  const candleRef     = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef     = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ema9Ref       = useRef<ISeriesApi<"Line"> | null>(null);
  const ema21Ref      = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref      = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiRef        = useRef<ISeriesApi<"Line"> | null>(null);
  const rsiOB         = useRef<ReturnType<ISeriesApi<"Line">["createPriceLine"]> | null>(null);
  const rsiOS         = useRef<ReturnType<ISeriesApi<"Line">["createPriceLine"]> | null>(null);
  const priceLineRefs = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]>[]>([]);
  const fittedRef     = useRef(false);

  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const CANDLE_H  = Math.round(height * 0.58);
    const VOLUME_H  = Math.round(height * 0.12);
    const RSI_H     = Math.round(height * 0.22);

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height: CANDLE_H + VOLUME_H + RSI_H,
      layout: {
        background:  { type: ColorType.Solid, color: "transparent" },
        textColor:   "#71717A",
        fontFamily:  "var(--font-jetbrains-mono), monospace",
        fontSize:    10,
      },
      grid: {
        vertLines: { color: "rgba(39,39,42,0.3)" },
        horzLines: { color: "rgba(39,39,42,0.3)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(212,168,67,0.4)", labelBackgroundColor: "#D4A843", width: 1, style: LineStyle.Dashed },
        horzLine: { color: "rgba(212,168,67,0.4)", labelBackgroundColor: "#D4A843", width: 1, style: LineStyle.Dashed },
      },
      rightPriceScale: { 
        borderColor: "rgba(39,39,42,0.5)", 
        scaleMargins: { top: 0.15, bottom: 0.15 },
        autoScale: true,
      },
      timeScale:       { borderColor: "rgba(39,39,42,0.5)", timeVisible: true, secondsVisible: false },
    });

    // Candlestick series
    const candle = chart.addSeries(CandlestickSeries, {
      upColor:        "#22C55E",
      downColor:      "#EF4444",
      borderUpColor:  "#22C55E",
      borderDownColor:"#EF4444",
      wickUpColor:    "#22C55E",
      wickDownColor:  "#EF4444",
      priceScaleId:   "right",
    });

    // Volume histogram (overlaid, scaled to bottom 20% of candle pane)
    const volume = chart.addSeries(HistogramSeries, {
      color:        "rgba(212,168,67,0.25)",
      priceFormat:  { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    // EMA lines
    const ema9  = chart.addSeries(LineSeries, { color: "#F59E0B", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    const ema21 = chart.addSeries(LineSeries, { color: "#3B82F6", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    const ema50 = chart.addSeries(LineSeries, { color: "#A855F7", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });

    // RSI pane
    const rsi = chart.addSeries(LineSeries, {
      color:          "#D4A843",
      lineWidth:      1,
      priceScaleId:   "rsi",
      priceLineVisible: false,
      lastValueVisible: true,
    });
    chart.priceScale("rsi").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0.02 },
      autoScale: true,
    });

    // RSI overbought/oversold lines
    const ob = rsi.createPriceLine({ price: 70, color: "rgba(239,68,68,0.4)",  lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "OB" });
    const os = rsi.createPriceLine({ price: 30, color: "rgba(34,197,94,0.4)",  lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false, title: "OS" });

    chartRef.current  = chart;
    candleRef.current = candle;
    volumeRef.current = volume;
    ema9Ref.current   = ema9;
    ema21Ref.current  = ema21;
    ema50Ref.current  = ema50;
    rsiRef.current    = rsi;
    rsiOB.current     = ob;
    rsiOS.current     = os;
    fittedRef.current = false;

    // Tooltip via crosshair move
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.point || !containerRef.current) {
        setTooltip(null);
        return;
      }
      const bar = param.seriesData.get(candle) as CandlestickData<Time> | undefined;
      if (!bar) { setTooltip(null); return; }

      const volBar = param.seriesData.get(volume) as { value: number } | undefined;
      const change    = bar.close - bar.open;
      const changePct = (change / bar.open) * 100;
      const ts = typeof bar.time === "number"
        ? new Date(bar.time * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
        : (bar.time as any).year ? `${(bar.time as any).year}-${(bar.time as any).month}-${(bar.time as any).day}` : String(bar.time);

      setTooltip({
        time: ts, open: bar.open, high: bar.high, low: bar.low, close: bar.close,
        volume: volBar?.value,
        change, changePct,
        x: param.point.x, y: param.point.y,
        containerWidth: containerRef.current?.clientWidth ?? 800,
        visible: true,
      });
    });

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);

    // Also observe container size changes (e.g. when side panels open/close)
    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    });
    ro.observe(containerRef.current);

    return () => {
      window.removeEventListener("resize", handleResize);
      ro.disconnect();
      chart.remove();
      chartRef.current = candleRef.current = volumeRef.current = null;
      ema9Ref.current = ema21Ref.current = ema50Ref.current = rsiRef.current = null;
      fittedRef.current = false;
    };
  }, [height]);

  // ── Update data ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!candleRef.current || !volumeRef.current || data.length === 0) return;

    candleRef.current.setData(data);

    // Volume bars coloured by candle direction
    volumeRef.current.setData(
      data.map((c) => ({
        time:  c.time,
        value: c.volume ?? 0,
        color: c.close >= c.open ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)",
      }))
    );

    // EMAs
    ema9Ref.current?.setData(calcEMA(data, 9));
    ema21Ref.current?.setData(calcEMA(data, 21));
    ema50Ref.current?.setData(calcEMA(data, 50));

    // RSI
    rsiRef.current?.setData(calcRSI(data, 14));

    // Fit only on first load
    if (!fittedRef.current) {
      chartRef.current?.timeScale().fitContent();
      fittedRef.current = true;
    }
  }, [data]);

  // ── Update signal lines ───────────────────────────────────────────────────
  useEffect(() => {
    if (!candleRef.current) return;
    priceLineRefs.current.forEach((pl) => {
      try { candleRef.current!.removePriceLine(pl); } catch { /* gone */ }
    });
    priceLineRefs.current = [];

    lines.forEach((line) => {
      if (!line.price || Number.isNaN(line.price)) return;
      const pl = candleRef.current!.createPriceLine({
        price:            line.price,
        color:            line.color,
        lineWidth:        1,
        lineStyle:        line.style ?? LineStyle.Dashed,
        axisLabelVisible: true,
        title:            line.label,
      });
      priceLineRefs.current.push(pl);
    });
  }, [lines]);

  return (
    <div className="relative w-full select-none">
      {/* EMA legend */}
      <div className="absolute top-2 left-2 z-10 flex items-center gap-3 pointer-events-none">
        {[
          { label: "EMA 9",  color: "#F59E0B" },
          { label: "EMA 21", color: "#3B82F6" },
          { label: "EMA 50", color: "#A855F7" },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1">
            <span className="h-px w-4 inline-block" style={{ backgroundColor: color }} />
            <span className="text-[9px] font-medium" style={{ color }}>{label}</span>
          </div>
        ))}
        <div className="flex items-center gap-1 ml-2">
          <span className="text-[9px] text-text-muted">RSI 14</span>
        </div>
      </div>

      {/* OHLCV Tooltip */}
      {tooltip && (
        <div
          className="absolute z-20 pointer-events-none glass rounded-lg px-3 py-2 text-[10px] font-[family-name:var(--font-jetbrains-mono)] shadow-lg"
          style={{
            left: tooltip.x > tooltip.containerWidth / 2 ? tooltip.x - 180 : tooltip.x + 12,
            top:  Math.max(4, tooltip.y - 60),
          }}
        >
          <div className="text-text-muted mb-1">{tooltip.time}</div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
            <span className="text-text-muted">O</span><span>{tooltip.open.toFixed(2)}</span>
            <span className="text-text-muted">H</span><span className="text-bullish">{tooltip.high.toFixed(2)}</span>
            <span className="text-text-muted">L</span><span className="text-bearish">{tooltip.low.toFixed(2)}</span>
            <span className="text-text-muted">C</span>
            <span className={tooltip.change >= 0 ? "text-bullish" : "text-bearish"}>
              {tooltip.close.toFixed(2)}
            </span>
          </div>
          <div className={`mt-1 ${tooltip.change >= 0 ? "text-bullish" : "text-bearish"}`}>
            {tooltip.change >= 0 ? "+" : ""}{tooltip.change.toFixed(2)} ({tooltip.changePct.toFixed(2)}%)
          </div>
          {tooltip.volume != null && tooltip.volume > 0 && (
            <div className="text-text-muted mt-0.5">Vol {tooltip.volume.toLocaleString()}</div>
          )}
        </div>
      )}

      <div ref={containerRef} className="w-full" />
    </div>
  );
}
