"use client";

import { TrendingUp, TrendingDown, AlertCircle } from "lucide-react";

interface Pattern {
  type: string;
  confidence: number;
  description: string;
}

interface PatternListProps {
  patterns: Pattern[];
}

export default function PatternList({ patterns }: PatternListProps) {
  if (!patterns || patterns.length === 0) {
    return (
      <div className="rounded-xl bg-surface/50 border border-border p-4">
        <div className="flex items-center gap-2 mb-2">
          <AlertCircle className="h-4 w-4 text-text-muted" />
          <h3 className="text-sm font-semibold">Pattern Recognition</h3>
        </div>
        <p className="text-xs text-text-muted">No patterns detected</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-surface/50 border border-border p-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertCircle className="h-4 w-4 text-gold" />
        <h3 className="text-sm font-semibold">Detected Patterns</h3>
        <span className="text-xs text-text-muted">({patterns.length})</span>
      </div>
      
      <div className="space-y-2">
        {patterns.map((pattern, i) => {
          const isBullish = pattern.description.toLowerCase().includes("bull") || 
                           pattern.description.toLowerCase().includes("buy");
          const isBearish = pattern.description.toLowerCase().includes("bear") || 
                           pattern.description.toLowerCase().includes("sell");
          
          return (
            <div
              key={i}
              className="flex items-start gap-3 rounded-lg bg-surface p-3 border border-border hover:border-gold/30 transition-colors"
            >
              <div className={`flex h-8 w-8 items-center justify-center rounded-lg shrink-0 ${
                isBullish ? "bg-bullish/10 border border-bullish/20" :
                isBearish ? "bg-bearish/10 border border-bearish/20" :
                "bg-warning/10 border border-warning/20"
              }`}>
                {isBullish ? (
                  <TrendingUp className="h-4 w-4 text-bullish" />
                ) : isBearish ? (
                  <TrendingDown className="h-4 w-4 text-bearish" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-warning" />
                )}
              </div>
              
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <h4 className="text-xs font-semibold truncate">{pattern.type}</h4>
                  <span className={`text-xs font-bold font-[family-name:var(--font-jetbrains-mono)] ${
                    pattern.confidence >= 75 ? "text-bullish" :
                    pattern.confidence >= 65 ? "text-gold" :
                    "text-text-muted"
                  }`}>
                    {pattern.confidence.toFixed(0)}%
                  </span>
                </div>
                <p className="text-[10px] text-text-muted leading-relaxed">
                  {pattern.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
      
      <div className="mt-3 pt-3 border-t border-border">
        <p className="text-[10px] text-text-muted">
          Patterns are detected using technical analysis of chart formations and candlestick structures.
          Higher confidence indicates stronger signal reliability.
        </p>
      </div>
    </div>
  );
}
