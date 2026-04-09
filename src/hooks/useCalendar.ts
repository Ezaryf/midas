"use client";

import { useQuery } from "@tanstack/react-query";
import type { CalendarEvent } from "@/lib/mock-data";
import { fetchWithSchema } from "@/lib/http";
import { calendarResponseSchema } from "@/lib/schemas/api";

export function useCalendar() {
  const query = useQuery({
    queryKey: ["calendar"],
    queryFn: async () => {
      const data = await fetchWithSchema("/api/calendar", calendarResponseSchema);
      return data.events as CalendarEvent[];
    },
    refetchInterval: 1_800_000,
  });

  return { events: query.data ?? [], loading: query.isLoading };
}
