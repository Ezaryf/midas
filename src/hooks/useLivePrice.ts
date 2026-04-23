"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useMidasStore } from "@/store/useMidasStore";
import { useShallow } from 'zustand/react/shallow';

const STALE_TICK_MS = 30_000;

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
  source?: string;
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
  const sessionDataRef = useRef<{ open: number; high: number; low: number } | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  
  const prevPriceRef = useRef<number | null>(null);
  const tickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTickTimeout = useCallback(() => {
    if (tickTimeoutRef.current) {
      clearTimeout(tickTimeoutRef.current);
      tickTimeoutRef.current = null;
    }
  }, []);

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

  // Detect price source (MT5 bridge vs AllTick fallback)
  const tickSource = currentPrice?.source || "";
  const isAllTickFallback = tickSource === "ALLTICK";
  
  // Extract primitives and apply calibration
  const rawBid = currentPrice?.bid ?? 0;
  const rawAsk = currentPrice?.ask ?? 0;
  
  const bid = rawBid * calibrationFactor;
  const ask = rawAsk * calibrationFactor;
  
  const time = currentPrice?.received_at ?? currentPrice?.time ?? "";
  const spread = Math.max(0, +(ask - bid).toFixed(2));

  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    clearTickTimeout();
    sessionDataRef.current = null;
    prevPriceRef.current = null;
    setTick(null);
  }, [activeSymbol, clearTickTimeout]);

  useEffect(() => {
    if (!isConnected || !isSymbolMatch || bid <= 1) {
      clearTickTimeout();
      setTick(null);
    }
  }, [bid, isConnected, isSymbolMatch, clearTickTimeout]);

  useEffect(() => {
    if (!isSymbolMatch || bid <= 1) return;

    // Update session data via ref (no re-render)
    if (!sessionDataRef.current) {
      prevPriceRef.current = null;
      sessionDataRef.current = { open: bid, high: bid, low: bid };
    } else if (bid > sessionDataRef.current.high) {
      sessionDataRef.current = { ...sessionDataRef.current, high: bid };
    } else if (bid < sessionDataRef.current.low) {
      sessionDataRef.current = { ...sessionDataRef.current, low: bid };
    }

    if (prevPriceRef.current !== null && prevPriceRef.current !== bid) {
      clearTickTimeout();
      setTick(bid >= prevPriceRef.current ? "up" : "down");
      tickTimeoutRef.current = setTimeout(() => {
        setTick(null);
        tickTimeoutRef.current = null;
      }, 300);
    }
    prevPriceRef.current = bid;

    return () => {
      clearTickTimeout();
    };
  }, [bid, isSymbolMatch, clearTickTimeout]);

  // Derive all data synchronously
  const result = useMemo(() => {
    const updatedAt = time || null;
    const updatedMs = updatedAt ? Date.parse(updatedAt) : NaN;
    const ageMs = Number.isFinite(updatedMs) ? Math.max(0, nowMs - updatedMs) : null;
    const isStale = isConnected && isSymbolMatch && ageMs !== null && ageMs > STALE_TICK_MS;

    const sessionData = sessionDataRef.current;
    
    if (!isConnected || !isSymbolMatch || bid <= 1 || !sessionData) {
      let error: string | null = null;
      if (!isConnected) {
        error = isAllTickFallback 
          ? "Using backup price feed (AllTick)" 
          : "Waiting for MT5 connection...";
      } else if (!isSymbolMatch) {
        error = `Symbol Mismatch (Midas: ${activeSymbol}, MT5: ${currentSymbol})`;
      } else if (isStale) {
        error = "Waiting for the next MT5 tick...";
      } else if (bid <= 1) {
        error = "Waiting for live tick...";
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
        source: tickSource,
      } as LivePrice,
      loading: false,
      error: isStale ? "Waiting for the next MT5 tick..." : null as string | null,
      isStale,
      ageMs,
      isSymbolMatch,
      currentSymbol,
      activeSymbol,
      tick,
    };
  }, [bid, ask, spread, time, isConnected, isSymbolMatch, activeSymbol, currentSymbol, nowMs, tick]);

  return result;
}
