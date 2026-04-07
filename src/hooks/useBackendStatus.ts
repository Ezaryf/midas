"use client";

import { useState, useEffect } from "react";

export type BackendStatus = "checking" | "online" | "offline";

export function useBackendStatus() {
  const [status, setStatus] = useState<BackendStatus>("checking");

  const check = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/health", {
        signal: AbortSignal.timeout(3000),
      });
      setStatus(res.ok ? "online" : "offline");
    } catch {
      setStatus("offline");
    }
  };

  useEffect(() => {
    check();
    const id = setInterval(check, 15_000);
    return () => clearInterval(id);
  }, []);

  return status;
}
