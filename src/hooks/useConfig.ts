"use client";

import { useState, useEffect } from "react";
import type { MidasConfig } from "@/lib/types";
import { DEFAULT_CONFIG } from "@/lib/types";
import { persistedConfigSchema } from "@/lib/schemas/api";

const LS_KEY = "midas_config";
const SS_KEY = "midas_secrets";
const SECRET_KEYS: (keyof MidasConfig)[] = ["mt5Password", "apiKey"];

export function useConfig() {
  const [config, setConfig] = useState<MidasConfig>(DEFAULT_CONFIG);
  const [loaded, setLoaded] = useState(false);

  // Load once on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      const secretRaw = sessionStorage.getItem(SS_KEY);
      const secrets = secretRaw ? JSON.parse(secretRaw) : {};
      if (raw) {
        const merged = { ...DEFAULT_CONFIG, ...JSON.parse(raw), ...secrets };
        const parsed = persistedConfigSchema.safeParse(merged);
        if (parsed.success) {
          setConfig(parsed.data);
        }
      }
    } catch { /* ignore */ }
    setLoaded(true);
  }, []);

  const save = (updates: Partial<MidasConfig>) => {
    const next = persistedConfigSchema.parse({ ...config, ...updates });
    setConfig(next);
    try {
      const publicConfig: Record<string, unknown> = { ...next };
      const secretConfig: Record<string, unknown> = {};
      for (const key of SECRET_KEYS) {
        secretConfig[key] = publicConfig[key];
        publicConfig[key] = "";
      }
      localStorage.setItem(LS_KEY, JSON.stringify(publicConfig));
      sessionStorage.setItem(SS_KEY, JSON.stringify(secretConfig));
    } catch { /* ignore */ }
    return next;
  };

  return { config, save, loaded };
}
