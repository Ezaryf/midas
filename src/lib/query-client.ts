import { QueryClient } from "@tanstack/react-query";
import { DEFAULT_QUERY_STALE_TIME, DEFAULT_QUERY_GC_TIME } from "./constants";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: DEFAULT_QUERY_STALE_TIME,
        gcTime: DEFAULT_QUERY_GC_TIME,
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}
