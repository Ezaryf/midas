"use client";

import { useQuery } from "@tanstack/react-query";
import type { NewsItem } from "@/lib/types";
import { fetchWithSchema } from "@/lib/http";
import { newsResponseSchema } from "@/lib/schemas/api";

export function useNews() {
  const query = useQuery({
    queryKey: ["news"],
    queryFn: async () => {
      const data = await fetchWithSchema("/api/news", newsResponseSchema);
      return data.items as NewsItem[];
    },
    refetchInterval: 300_000,
  });

  return { items: query.data ?? [], loading: query.isLoading };
}
