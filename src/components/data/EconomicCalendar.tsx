"use client";

import type { CalendarEvent } from "@/lib/mock-data";
import { AlertTriangle } from "lucide-react";

interface EconomicCalendarProps {
  events: CalendarEvent[];
}

const impactConfig = {
  high: { color: "text-bearish", bg: "bg-bearish/10", label: "🔴 High" },
  medium: { color: "text-warning", bg: "bg-warning/10", label: "🟡 Medium" },
  low: { color: "text-text-muted", bg: "bg-surface", label: "🟢 Low" },
};

function formatEventTime(date: Date | string): string {
  const d = typeof date === "string" ? new Date(date) : date;
  const now = new Date();
  const diff = d.getTime() - now.getTime();
  const isPast = diff < 0;

  if (isPast) {
    const mins = Math.abs(Math.floor(diff / 60000));
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    return `${hrs}h ago`;
  }

  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `in ${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `in ${hrs}h`;
  const days = Math.floor(hrs / 24);
  return `in ${days}d`;
}

export default function EconomicCalendar({ events }: EconomicCalendarProps) {
  const sortedEvents = [...events].sort((a, b) => {
    const at = typeof a.scheduledAt === "string" ? new Date(a.scheduledAt) : a.scheduledAt;
    const bt = typeof b.scheduledAt === "string" ? new Date(b.scheduledAt) : b.scheduledAt;
    return at.getTime() - bt.getTime();
  });

  return (
    <div className="space-y-2">
      {sortedEvents.map((event) => {
        const d = typeof event.scheduledAt === "string" ? new Date(event.scheduledAt) : event.scheduledAt;
        const impact = impactConfig[event.impact];
        const isPast = d.getTime() < Date.now();
        const isUpcoming = !isPast && d.getTime() - Date.now() < 2 * 3600000;

        return (
          <div
            key={event.id}
            className={`rounded-xl p-3 transition-colors ${
              isUpcoming
                ? "bg-warning/5 border border-warning/20"
                : "bg-surface/50 hover:bg-surface"
            } ${isPast ? "opacity-60" : ""}`}
          >
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold text-text-muted bg-surface rounded px-1.5 py-0.5">
                  {event.country}
                </span>
                <span className="text-[10px]">{impact.label}</span>
              </div>
              <div className="flex items-center gap-1">
                {isUpcoming && (
                  <AlertTriangle className="h-3 w-3 text-warning animate-pulse" />
                )}
                <span
                  className={`text-[10px] font-medium ${
                    isUpcoming ? "text-warning" : "text-text-muted"
                  }`}
                >
                  {formatEventTime(event.scheduledAt)}
                </span>
              </div>
            </div>
            <h4 className="text-sm font-medium mb-2">{event.title}</h4>
            <div className="flex items-center gap-4">
              <div>
                <span className="text-[10px] text-text-muted">Forecast</span>
                <p className="text-xs font-medium font-[family-name:var(--font-jetbrains-mono)]">
                  {event.forecast}
                </p>
              </div>
              <div>
                <span className="text-[10px] text-text-muted">Previous</span>
                <p className="text-xs font-medium font-[family-name:var(--font-jetbrains-mono)]">
                  {event.previous}
                </p>
              </div>
              {event.actual && (
                <div>
                  <span className="text-[10px] text-text-muted">Actual</span>
                  <p className="text-xs font-bold font-[family-name:var(--font-jetbrains-mono)] text-gold">
                    {event.actual}
                  </p>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
