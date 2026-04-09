"use client";

import { useState, useEffect } from "react";
import type { MidasConfig } from "@/lib/types";
import { DEFAULT_CONFIG } from "@/lib/types";
import { persistedConfigSchema } from "@/lib/schemas/api";

const LS_KEY = "midas_config"; // everything in localStorage — persists across sessions

export function useConfig() {
  const [config, setConfig] = useState<MidasConfig>(DEFAULT_CONFIG);
  const [loaded, setLoaded] = useState(false);

  // Load once on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) {
        const parsed = persistedConfigSchema.safeParse({ ...DEFAULT_CONFIG, ...JSON.parse(raw) });
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
      localStorage.setItem(LS_KEY, JSON.stringify(next));
    } catch { /* ignore */ }
    return next;
  };

  return { config, save, loaded };
}
