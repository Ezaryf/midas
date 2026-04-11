'use client';

import { startTransition, useEffect, useRef } from 'react';
import { useMidasStore, type PriceUpdate, type TradeSignal } from '@/store/useMidasStore';
import type { AnalysisBatch } from '@/lib/types';
import { getWsUrl } from '@/lib/config';

const RETRY_DELAY = 5000;

export const useSocket = () => {
  const socketRef  = useRef<WebSocket | null>(null);
  const retryRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    const connect = () => {
      if (!mountedRef.current) return;

      // Clean up any existing socket
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.onerror = null;
        socketRef.current.close();
      }

      const ws = new WebSocket(getWsUrl());
      socketRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        useMidasStore.getState().setConnected(true);
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const payload = JSON.parse(event.data);
          const store = useMidasStore.getState();
          if (payload.type === 'TICK') {
            store.setPrice(payload.data as PriceUpdate);
          } else if (payload.type === 'SIGNAL_BATCH') {
            const batch = payload.data as AnalysisBatch;
            if (!batch?.primary) return;
            startTransition(() => {
              store.setAnalysisBatch(batch);
              store.addSignalToHistory(batch.primary);
              batch.backups?.forEach((backup) => store.addSignalToHistory(backup));
            });
          } else if (payload.type === 'SIGNAL') {
            const signal = payload.data as TradeSignal;
            if (!signal.trading_style) signal.trading_style = 'Scalper';
            startTransition(() => {
              store.setActiveSignal(signal);
              store.addSignalToHistory(signal);
            });
            
            // Show notification
            if (Notification.permission === 'granted') {
              new Notification(`Midas Signal: ${signal.direction}`, {
                body: `${signal.reasoning.substring(0, 80)}... (Confidence: ${signal.confidence}%)`,
                icon: '/favicon.ico',
              });
            }
            
            // Log to console for debugging
            console.log(`[Midas] New ${signal.trading_style} signal: ${signal.direction} @ ${signal.entry_price} (${signal.confidence}% confidence)`);
          } else if (payload.type === 'MARKET_STATE') {
            const ms = payload.data;
            if (ms) store.setMarketState(ms);
          }
        } catch {
          // Malformed message — ignore silently
        }
      };


      ws.onclose = (e) => {
        if (!mountedRef.current) return;
        useMidasStore.getState().setConnected(false);
        // Only retry on abnormal closure (not intentional unmount close)
        if (e.code !== 1000) {
          retryRef.current = setTimeout(connect, RETRY_DELAY);
        }
      };

      // onerror always fires before onclose — just close, let onclose handle retry
      // Don't log: the error object is always empty ({}) and adds noise
      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      mountedRef.current = false;
      if (retryRef.current) clearTimeout(retryRef.current);
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.onerror = null;
        socketRef.current.close(1000, 'Component unmounted');
      }
    };
  }, []); // No dependencies — WebSocket lifecycle is fully ref-based
};
