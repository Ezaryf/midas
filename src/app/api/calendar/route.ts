import { NextResponse } from "next/server";

const FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json";

interface ForexFactoryEvent {
  country?: string;
  impact?: string;
  title?: string;
  forecast?: string;
  previous?: string;
  actual?: string;
  date?: string;
}

export async function GET() {
  try {
    const res = await fetch(FF_URL, {
      next: { revalidate: 1800 }, // cache 30 min
      headers: { "User-Agent": "Mozilla/5.0" },
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as ForexFactoryEvent[];

    // Filter USD + high/medium impact only
    const events = data
      .filter((e) => e.country === "USD" && e.impact !== "Low")
      .map((e, i) => ({
        id:          `ff-${i}`,
        title:       e.title ?? "Untitled event",
        country:     e.country ?? "USD",
        impact:      (e.impact as string).toLowerCase() as "high" | "medium" | "low",
        forecast:    e.forecast || "-",
        previous:    e.previous || "-",
        actual:      e.actual || undefined,
        scheduledAt: e.date ?? new Date().toISOString(),
      }));

    return NextResponse.json({ events });
  } catch (e) {
    console.error("Calendar fetch error:", e);
    return NextResponse.json({ events: [] });
  }
}
