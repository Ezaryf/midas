"use client";

import { useState, useEffect } from "react";
import type { NewsItem } from "@/lib/mock-data";

export function useNews() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/news")
      .then(r => r.json())
      .then(data => {
        const mapped: NewsItem[] = (data.items ?? []).map((n: any) => ({
          ...n,
          publishedAt: new Date(n.publishedAt),
        }));
        setItems(mapped);
      })
      .catch(console.error)
      .finally(() => setLoading(false));

    // Refresh every 5 minutes
    const id = setInterval(() => {
      fetch("/api/news")
        .then(r => r.json())
        .then(data => setItems((data.items ?? []).map((n: any) => ({ ...n, publishedAt: new Date(n.publishedAt) }))));
    }, 300_000);

    return () => clearInterval(id);
  }, []);

  return { items, loading };
}
