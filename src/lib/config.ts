export const config = {
  backend: {
    http: process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000",
    ws: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000",
  },
  api: {
    health: "/api/health",
    signals: {
      generate: "/api/signals/force-generate",
      execute: "/api/signals/execute",
    },
    settings: "/api/settings",
    positions: "/api/positions/open",
    targetSymbol: "/api/target-symbol",
    tradingStyle: "/api/trading-style",
    mt5Validate: "/api/mt5/validate",
  },
  ws: {
    mt5: "/ws/mt5",
  },
} as const;

export function getBackendUrl(path: string): string {
  return `${config.backend.http}${path}`;
}

export function getWsUrl(path: string = config.ws.mt5): string {
  return `${config.backend.ws}${path}`;
}