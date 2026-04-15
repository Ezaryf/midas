'use client';

import { startTransition, useEffect, useRef } from 'react';
import { useMidasStore, type PriceUpdate, type TradeSignal } from '@/store/useMidasStore';
import type { AnalysisBatch } from '@/lib/types';

const BASE_RETRY_DELAY = 2000;
const MAX_RETRY_DELAY = 10000;

// Backend WebSocket server (port 8000)
// Connects to /ws/frontend endpoint for browser connections
const WS_URLS = [
  'ws://localhost:8000/ws/frontend',
  'ws://127.0.0.1:8000/ws/frontend',
];

export const useSocket = () => {
  const socketRef  = useRef<WebSocket | null>(null);
  const retryRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const retryCountRef = useRef(0);
  const urlIndexRef = useRef(0);

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

      const wsUrl = WS_URLS[urlIndexRef.current];
      console.log(`[WebSocket] Connecting to ${wsUrl} (attempt ${retryCountRef.current + 1})`);
      
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.binaryType = 'arraybuffer';

// Send PING every 25 seconds to keep connection alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'PING' }));
        }
      }, 25000);

      ws.onopen = () => {
        if (!mountedRef.current) return;
        console.log(`[WebSocket] Connected to ${wsUrl}`);
        useMidasStore.getState().setConnected(true);
        retryCountRef.current = 0;
        urlIndexRef.current = 0;
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
            
            if (Notification.permission === 'granted') {
              new Notification(`Midas Signal: ${signal.direction}`, {
                body: `${signal.reasoning.substring(0, 80)}... (Confidence: ${signal.confidence}%)`,
                icon: '/favicon.ico',
              });
            }
            
            console.log(`[Midas] New ${signal.trading_style} signal: ${signal.direction} @ ${signal.entry_price} (${signal.confidence}% confidence)`);
          } else if (payload.type === 'MARKET_STATE') {
            const ms = payload.data;
            if (ms) store.setMarketState(ms);
          } else if (payload.type === 'PONG') {
            // Heartbeat response received
          }
        } catch {
          // Malformed message — ignore silently
        }
      };

      ws.onclose = (e) => {
        clearInterval(pingInterval);
        if (!mountedRef.current) return;
        useMidasStore.getState().setConnected(false);
        
        // Log close event for debugging
        console.log(`[WebSocket] Closed (code: ${e.code}, reason: ${e.reason || 'none'})`);
        
        // Only retry on abnormal closure (not intentional unmount close)
        if (e.code !== 1000) {
          // Try next URL if current one failed
          if (urlIndexRef.current < WS_URLS.length - 1) {
            urlIndexRef.current += 1;
            console.log(`[WebSocket] Trying fallback URL: ${WS_URLS[urlIndexRef.current]}`);
            retryRef.current = setTimeout(connect, 1000);
          } else {
            // All URLs failed, use exponential backoff
            urlIndexRef.current = 0;
            const delay = Math.min(BASE_RETRY_DELAY * Math.pow(2, retryCountRef.current), MAX_RETRY_DELAY);
            retryCountRef.current += 1;
            console.log(`[WebSocket] Retrying in ${delay}ms (attempt ${retryCountRef.current})`);
            retryRef.current = setTimeout(connect, delay);
          }
        }
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
