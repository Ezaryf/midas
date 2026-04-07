import { NextResponse } from "next/server";

const FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json";

export async function GET() {
  try {
    const res = await fetch(FF_URL, {
      next: { revalidate: 1800 }, // cache 30 min
      headers: { "User-Agent": "Mozilla/5.0" },
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Filter USD + high/medium impact only
    const events = (data as any[])
      .filter((e) => e.country === "USD" && e.impact !== "Low")
      .map((e, i) => ({
        id:          `ff-${i}`,
        title:       e.title,
        country:     e.country,
        impact:      (e.impact as string).toLowerCase() as "high" | "medium" | "low",
        forecast:    e.forecast || "-",
        previous:    e.previous || "-",
        actual:      e.actual || undefined,
        scheduledAt: e.date, // ISO string from FF
      }));

    return NextResponse.json({ events });
  } catch (e) {
    console.error("Calendar fetch error:", e);
    return NextResponse.json({ events: [] });
  }
}
