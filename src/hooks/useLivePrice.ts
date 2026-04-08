"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useMidasStore } from "@/store/useMidasStore";
import { useShallow } from 'zustand/react/shallow';

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
  const { currentPrice, targetSymbol, isConnected } = useMidasStore(useShallow(s => ({
    currentPrice: s.currentPrice,
    targetSymbol: s.targetSymbol,
    isConnected: s.isConnected
  })));
  
  const [tick, setTick] = useState<"up" | "down" | null>(null);

  // Track session open price (first price of the session)
  const [sessionData, setSessionData] = useState<{ open: number; high: number; low: number } | null>(null);
  
  const prevPriceRef = useRef<number | null>(null);
  const tickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derive symbols to check for mismatches
  const currentSymbol = (currentPrice?.symbol || "XAUUSD").toUpperCase();
  const activeSymbol = (targetSymbol || "XAUUSD").toUpperCase();
  const isSymbolMatch = isConnected && currentSymbol === activeSymbol;
  
  const [prevActiveSymbol, setPrevActiveSymbol] = useState(activeSymbol);

  // Extract primitives
  const bid = currentPrice?.bid ?? 0;
  const ask = currentPrice?.ask ?? 0;
  const time = currentPrice?.time ?? "";

  // Reset session tracking when symbol changes (React 18+ idiom)
  if (activeSymbol !== prevActiveSymbol) {
    setPrevActiveSymbol(activeSymbol);
    setSessionData(null);
  }

  useEffect(() => {
    if (!isSymbolMatch || bid <= 1) return;

    setSessionData(prev => {
      if (!prev) {
        prevPriceRef.current = null;
        return { open: bid, high: bid, low: bid };
      }
      if (prev.open === bid && prev.high >= bid && prev.low <= bid) return prev; // Avoid unnecessary updates
      return {
        open: prev.open,
        high: Math.max(prev.high, bid),
        low: Math.min(prev.low, bid)
      };
    });

    if (prevPriceRef.current !== null && prevPriceRef.current !== bid) {
      if (tickTimeoutRef.current) clearTimeout(tickTimeoutRef.current);
      setTick(bid >= prevPriceRef.current ? "up" : "down");
      tickTimeoutRef.current = setTimeout(() => setTick(null), 300);
    }
    prevPriceRef.current = bid;

    return () => {
      if (tickTimeoutRef.current) clearTimeout(tickTimeoutRef.current);
    };
  }, [bid, isSymbolMatch]);

  // Derive all data synchronously
  const result = useMemo(() => {
    if (!isConnected || !isSymbolMatch || bid <= 1 || !sessionData) {
      let error: string | null = null;
      if (!isConnected) {
        error = "MT5 Bridge Offline";
      } else if (!isSymbolMatch) {
        error = `Symbol Mismatch (Midas: ${activeSymbol}, MT5: ${currentSymbol})`;
      }

      return {
        data: null as LivePrice | null,
        loading: isConnected && isSymbolMatch && bid > 1 && !sessionData,
        error,
        tick,
      };
    }

    const change = +(bid - sessionData.open).toFixed(2);
    const changePercent = +((change / sessionData.open) * 100).toFixed(2);

    return {
      data: {
        price: bid,
        change,
        changePercent,
        high: sessionData.high,
        low: sessionData.low,
        bid,
        ask,
        updatedAt: time || new Date().toISOString(),
      } as LivePrice,
      loading: false,
      error: null as string | null,
      tick,
    };
  }, [bid, ask, time, isConnected, isSymbolMatch, activeSymbol, sessionData, tick, currentSymbol]);

  return result;
}
