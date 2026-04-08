"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useMidasStore } from "@/store/useMidasStore";
import { useShallow } from 'zustand/react/shallow';

const STALE_TICK_MS = 8_000;

export interface LivePrice {
  price: number;
  change: number;
  changePercent: number;
  high: number;
  low: number;
  bid: number;
  ask: number;
  spread: number;
  updatedAt: string;
}

export function useLivePrice() {
  const { currentPrice, targetSymbol, isConnected, calibrationFactor } = useMidasStore(useShallow(s => ({
    currentPrice: s.currentPrice,
    targetSymbol: s.targetSymbol,
    isConnected: s.isConnected,
    calibrationFactor: s.calibrationFactor
  })));
  
  const [tick, setTick] = useState<"up" | "down" | null>(null);

  // Track session open price (first price of the session)
  const [sessionData, setSessionData] = useState<{ open: number; high: number; low: number } | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  
  const prevPriceRef = useRef<number | null>(null);
  const tickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derive symbols to check for mismatches
  const normalizeSymbol = (s: string) => 
    s.toUpperCase()
     .replace(/[^A-Z0-9]/g, '') // Remove dots, slashes, etc.
     .replace(/^GOLD$|^XAUUSD$|^XAUUSD[A-Z]$|^GC[A-Z0-9]+$/g, 'XAUUSD'); // Map all gold variants to XAUUSD

  const currentSymbolRaw = currentPrice?.symbol || "";
  const currentSymbolNormalized = normalizeSymbol(currentSymbolRaw || "XAUUSD");
  const activeSymbolNormalized = normalizeSymbol(targetSymbol || "XAUUSD");
  
  // For display in error messages
  const currentSymbol = currentSymbolRaw.toUpperCase();
  const activeSymbol = (targetSymbol || "XAUUSD").toUpperCase();

  const isSymbolMatch = isConnected && (
    !currentSymbolRaw || // If no data yet, assume match for loading states
    currentSymbolNormalized === activeSymbolNormalized
  );

  // Extract primitives and apply calibration
  const rawBid = currentPrice?.bid ?? 0;
  const rawAsk = currentPrice?.ask ?? 0;
  
  const bid = rawBid * calibrationFactor;
  const ask = rawAsk * calibrationFactor;
  
  const time = currentPrice?.time ?? "";
  const spread = Math.max(0, +(ask - bid).toFixed(2));

  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    setSessionData(null);
    prevPriceRef.current = null;
    setTick(null);
  }, [activeSymbol]);

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
    const updatedAt = time || null;
    const updatedMs = updatedAt ? Date.parse(updatedAt) : NaN;
    const ageMs = Number.isFinite(updatedMs) ? Math.max(0, nowMs - updatedMs) : null;
    const isStale = isConnected && isSymbolMatch && ageMs !== null && ageMs > STALE_TICK_MS;

    if (!isConnected || !isSymbolMatch || bid <= 1 || !sessionData) {
      let error: string | null = null;
      if (!isConnected) {
        error = "MT5 Bridge Offline";
      } else if (!isSymbolMatch) {
        error = `Symbol Mismatch (Midas: ${activeSymbol}, MT5: ${currentSymbol})`;
      } else if (isStale) {
        error = "Live feed stale";
      }

      return {
        data: null as LivePrice | null,
        loading: isConnected && isSymbolMatch && bid > 1 && !sessionData,
        error,
        isStale,
        ageMs,
        isSymbolMatch,
        currentSymbol,
        activeSymbol,
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
        spread,
        updatedAt: updatedAt || new Date().toISOString(),
      } as LivePrice,
      loading: false,
      error: isStale ? "Live feed stale" : null as string | null,
      isStale,
      ageMs,
      isSymbolMatch,
      currentSymbol,
      activeSymbol,
      tick,
    };
  }, [bid, ask, spread, time, isConnected, isSymbolMatch, activeSymbol, sessionData, tick, currentSymbol, nowMs]);

  return result;
}
