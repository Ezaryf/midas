"use client";

import { useState, useEffect, useRef } from "react";
import { useMidasStore } from "@/store/useMidasStore";

export interface LivePrice {
  price: number;
  change: number;
  changePercent: number;
  high: number;
  low: number;
  bid: number;
  ask: number;
  updatedAt: string;
}

export function useLivePrice() {
  const currentPrice = useMidasStore(s => s.currentPrice);
  const isConnected = useMidasStore(s => s.isConnected);
  
  const [data, setData] = useState<LivePrice | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState<"up" | "down" | null>(null);

  // Track session open price (first price of the session)
  const sessionOpenRef = useRef<number | null>(null);
  const sessionHighRef = useRef<number | null>(null);
  const sessionLowRef = useRef<number | null>(null);
  const prevPriceRef = useRef<number | null>(null);

  useEffect(() => {
    if (!currentPrice || !isConnected || currentPrice.bid <= 1.0 || currentPrice.ask <= 1.0) {
      setError("MT5 not connected or waiting for valid quote");
      setLoading(false);
      return;
    }

    const price = currentPrice.bid;

    // Initialize session tracking on first price
    if (sessionOpenRef.current === null) {
      sessionOpenRef.current = price;
      sessionHighRef.current = price;
      sessionLowRef.current = price;
    }

    // Update session high/low
    sessionHighRef.current = Math.max(sessionHighRef.current!, price);
    sessionLowRef.current = Math.min(sessionLowRef.current!, price);

    // Tick flash direction
    if (prevPriceRef.current !== null && prevPriceRef.current !== price) {
      setTick(price >= prevPriceRef.current ? "up" : "down");
      setTimeout(() => setTick(null), 300); // Faster flash for real-time feel
    }
    prevPriceRef.current = price;

    const change = parseFloat((price - sessionOpenRef.current!).toFixed(2));
    const changePercent = parseFloat(
      ((change / sessionOpenRef.current!) * 100).toFixed(2)
    );

    setData({
      price,
      change,
      changePercent,
      high: sessionHighRef.current!,
      low: sessionLowRef.current!,
      bid: currentPrice.bid,
      ask: currentPrice.ask,
      updatedAt: currentPrice.time || new Date().toISOString(),
    });

    setError(null);
    setLoading(false);
  }, [currentPrice, isConnected]);

  return { data, loading, error, tick };
}
