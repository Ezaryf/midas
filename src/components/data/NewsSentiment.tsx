"use client";

import type { NewsItem } from "@/lib/types";
import { TrendingUp, TrendingDown, Minus, ExternalLink } from "lucide-react";
import { formatRelativeTime } from "@/lib/utils";

interface NewsSentimentProps {
  items: NewsItem[];
}

const sentimentConfig = {
  bullish: {
    icon: TrendingUp,
    label: "Bullish",
    color: "text-bullish",
    bg: "bg-bullish/10 border-bullish/20",
  },
  bearish: {
    icon: TrendingDown,
    label: "Bearish",
    color: "text-bearish",
    bg: "bg-bearish/10 border-bearish/20",
  },
  neutral: {
    icon: Minus,
    label: "Neutral",
    color: "text-text-muted",
    bg: "bg-surface border-border",
  },
};

export default function NewsSentiment({ items }: NewsSentimentProps) {
  return (
    <div className="space-y-2">
      {items.map((item) => {
        const sentiment = sentimentConfig[item.sentiment];
        const SentimentIcon = sentiment.icon;

        return (
          <div
            key={item.id}
            className="group rounded-xl bg-surface/50 hover:bg-surface p-3 transition-colors cursor-default"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <div
                    className={`flex items-center gap-1 rounded-md border px-1.5 py-0.5 ${sentiment.bg}`}
                  >
                    <SentimentIcon className={`h-3 w-3 ${sentiment.color}`} />
                    <span
                      className={`text-[10px] font-medium ${sentiment.color}`}
                    >
                      {sentiment.label}
                    </span>
                  </div>
                  {item.impact === "high" && (
                    <span className="text-[10px] font-medium text-warning bg-warning/10 border border-warning/20 rounded-md px-1.5 py-0.5">
                      High Impact
                    </span>
                  )}
                </div>
                <h4 className="text-sm font-medium leading-snug mb-1 line-clamp-2">
                  {item.title}
                </h4>
                <p className="text-xs text-text-muted line-clamp-1">
                  {item.summary}
                </p>
              </div>
              <ExternalLink className="h-3.5 w-3.5 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity shrink-0 mt-1" />
            </div>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] text-text-muted">{item.source}</span>
              <span className="text-[10px] text-text-muted">·</span>
              <span className="text-[10px] text-text-muted">
                {formatRelativeTime(item.publishedAt)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
