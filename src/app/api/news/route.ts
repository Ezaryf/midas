import { NextResponse } from "next/server";

const GOLD_KEYWORDS = ["gold","xau","bullion","fed","inflation","cpi","fomc","dollar","rate","treasury","safe haven","geopolit"];

const BULLISH = ["surge","rally","rise","gain","jump","soar","climb","bullish","safe haven","dovish","rate cut","weak dollar","uncertainty","record"];
const BEARISH = ["fall","drop","decline","plunge","sink","bearish","hawkish","rate hike","strong dollar","sell-off","pressure"];

const FEEDS = [
  { url: "https://feeds.reuters.com/reuters/businessNews", source: "Reuters" },
  { url: "https://www.investing.com/rss/news_301.rss",     source: "Investing.com" },
  { url: "https://www.fxstreet.com/rss/news",              source: "FXStreet" },
];

function sentiment(text: string) {
  const t = text.toLowerCase();
  const b = BULLISH.filter(w => t.includes(w)).length;
  const r = BEARISH.filter(w => t.includes(w)).length;
  return b > r ? "bullish" : r > b ? "bearish" : "neutral";
}

function impact(title: string): "high" | "medium" | "low" {
  const t = title.toLowerCase();
  if (["fed","fomc","cpi","nfp","payroll","rate","inflation","gdp","war","crisis"].some(w => t.includes(w))) return "high";
  if (["gold","xau","dollar","treasury","yield"].some(w => t.includes(w))) return "medium";
  return "low";
}

function isRelevant(title: string, desc: string) {
  return GOLD_KEYWORDS.some(k => (title + desc).toLowerCase().includes(k));
}

async function parseFeed(feed: { url: string; source: string }) {
  const items: object[] = [];
  try {
    const res = await fetch(feed.url, { headers: { "User-Agent": "Mozilla/5.0" }, next: { revalidate: 120 } });
    if (!res.ok) return items;
    const text = await res.text();
    const matches = [...text.matchAll(/<item>([\s\S]*?)<\/item>/g)];
    for (const [, raw] of matches.slice(0, 20)) {
      const title   = raw.match(/<title><!\[CDATA\[(.*?)\]\]><\/title>/)?.[1] ?? raw.match(/<title>(.*?)<\/title>/)?.[1] ?? "";
      const desc    = raw.match(/<description><!\[CDATA\[(.*?)\]\]><\/description>/)?.[1] ?? raw.match(/<description>(.*?)<\/description>/)?.[1] ?? "";
      const link    = raw.match(/<link>(.*?)<\/link>/)?.[1] ?? "";
      const pubDate = raw.match(/<pubDate>(.*?)<\/pubDate>/)?.[1] ?? "";
      if (!isRelevant(title, desc)) continue;
      items.push({ id: `${feed.source}-${items.length}`, title: title.trim(), source: feed.source,
        sentiment: sentiment(title + desc), impact: impact(title),
        summary: desc.replace(/<[^>]+>/g, "").slice(0, 200).trim(),
        url: link.trim(), publishedAt: pubDate ? new Date(pubDate).toISOString() : new Date().toISOString() });
      if (items.length >= 5) break;
    }
  } catch { /* feed unavailable */ }
  return items;
}

export async function GET() {
  const results = await Promise.allSettled(FEEDS.map(parseFeed));
  const items = results.flatMap(r => r.status === "fulfilled" ? r.value : []);
  items.sort((a: any, b: any) => new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime());
  return NextResponse.json({ items: items.slice(0, 20) });
}
