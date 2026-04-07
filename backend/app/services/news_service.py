import logging
import asyncio
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import TypedDict

logger = logging.getLogger(__name__)

GOLD_KEYWORDS = [
    "gold", "xau", "xauusd", "bullion", "precious metal",
    "fed", "federal reserve", "inflation", "cpi", "fomc",
    "dollar", "usd", "rate cut", "rate hike", "treasury",
    "geopolit", "safe haven", "risk off",
]

RSS_FEEDS = [
    {"url": "https://feeds.reuters.com/reuters/businessNews", "source": "Reuters"},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories", "source": "MarketWatch"},
    {"url": "https://www.investing.com/rss/news_301.rss", "source": "Investing.com"},
    {"url": "https://www.fxstreet.com/rss/news", "source": "FXStreet"},
]

BULLISH_WORDS = [
    "surge", "rally", "rise", "gain", "jump", "soar", "climb", "bullish",
    "safe haven", "demand", "dovish", "rate cut", "weak dollar", "geopolit",
    "uncertainty", "inflation", "record", "high",
]
BEARISH_WORDS = [
    "fall", "drop", "decline", "plunge", "sink", "bearish", "hawkish",
    "rate hike", "strong dollar", "sell-off", "loss", "low", "pressure",
]


class NewsItem(TypedDict):
    id: str
    title: str
    source: str
    sentiment: str   # bullish | bearish | neutral
    impact: str      # high | medium | low
    summary: str
    url: str
    publishedAt: str


def _score_sentiment(text: str) -> str:
    t = text.lower()
    bull = sum(1 for w in BULLISH_WORDS if w in t)
    bear = sum(1 for w in BEARISH_WORDS if w in t)
    if bull > bear:
        return "bullish"
    if bear > bull:
        return "bearish"
    return "neutral"


def _is_relevant(title: str, summary: str) -> bool:
    combined = (title + " " + summary).lower()
    return any(kw in combined for kw in GOLD_KEYWORDS)


def _impact_level(title: str) -> str:
    high_words = ["fed", "fomc", "cpi", "nfp", "payroll", "rate", "inflation", "gdp", "war", "crisis"]
    t = title.lower()
    if any(w in t for w in high_words):
        return "high"
    if any(w in t for w in ["dollar", "gold", "xau", "treasury", "yield"]):
        return "medium"
    return "low"


async def _fetch_feed(client: httpx.AsyncClient, feed: dict) -> list[NewsItem]:
    items: list[NewsItem] = []
    try:
        r = await client.get(feed["url"], timeout=8.0, follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        channel = root.find("channel")
        if channel is None:
            return items

        for i, item in enumerate(channel.findall("item")):
            title   = (item.findtext("title") or "").strip()
            summary = (item.findtext("description") or "").strip()
            link    = (item.findtext("link") or "").strip()
            pub     = (item.findtext("pubDate") or "").strip()

            if not _is_relevant(title, summary):
                continue

            # Parse date
            try:
                dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z")
                published_at = dt.isoformat()
            except Exception:
                published_at = datetime.now(timezone.utc).isoformat()

            items.append(NewsItem(
                id=f"{feed['source']}-{i}",
                title=title,
                source=feed["source"],
                sentiment=_score_sentiment(title + " " + summary),
                impact=_impact_level(title),
                summary=summary[:200] if summary else title,
                url=link,
                publishedAt=published_at,
            ))

            if len(items) >= 5:
                break

    except Exception as e:
        logger.warning(f"Failed to fetch {feed['source']}: {e}")

    return items


class NewsService:
    async def get_gold_news(self) -> list[NewsItem]:
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
            results = await asyncio.gather(
                *[_fetch_feed(client, feed) for feed in RSS_FEEDS],
                return_exceptions=True,
            )

        all_items: list[NewsItem] = []
        for r in results:
            if isinstance(r, list):
                all_items.extend(r)

        # Sort by date descending, cap at 20
        all_items.sort(key=lambda x: x["publishedAt"], reverse=True)
        return all_items[:20]
