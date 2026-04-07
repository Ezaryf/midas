"use client";

import { useState, useEffect } from "react";
import type { CalendarEvent } from "@/lib/mock-data";
export function useCalendar() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/calendar")
      .then(r => r.json())
      .then(data => {
        const mapped: CalendarEvent[] = (data.events ?? []).map((e: CalendarEvent & { scheduledAt: string }) => ({
          ...e,
          scheduledAt: new Date(e.scheduledAt),
        }));
        setEvents(mapped);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return { events, loading };
}
