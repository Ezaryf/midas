"use client";

import { useState, useEffect } from "react";

export interface Position {
  ticket: number;
  symbol: string;
  type: string;
  volume: number;
  open_price: number;
  current_price: number;
  sl: number;
  tp: number;
  profit: number;
  swap: number;
  commission: number;
  open_time: string;
  comment: string;
}

export function usePositions(refreshInterval: number = 5000) {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchPositions = async () => {
      try {
        const response = await fetch("/api/positions");
        if (!response.ok) throw new Error("Failed to fetch positions");
        
        const data = await response.json();
        setPositions(data.positions || []);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };

    fetchPositions();
    const interval = setInterval(fetchPositions, refreshInterval);

    return () => clearInterval(interval);
  }, [refreshInterval]);

  return { positions, loading, error };
}
