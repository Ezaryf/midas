'use client';

import { useEffect, useRef } from 'react';
import { useMidasStore, type PriceUpdate, type TradeSignal } from '@/store/useMidasStore';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/mt5';
const RETRY_DELAY = 5000;

export const useSocket = () => {
  const socketRef  = useRef<WebSocket | null>(null);
  const retryRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

<<<<<<< HEAD
=======
  const { setPrice, setActiveSignal, addSignalToHistory, setConnected } = useMidasStore();

>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
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

      const ws = new WebSocket(WS_URL);
      socketRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
<<<<<<< HEAD
        useMidasStore.getState().setConnected(true);
=======
        setConnected(true);
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const payload = JSON.parse(event.data);
<<<<<<< HEAD
          const store = useMidasStore.getState();
          if (payload.type === 'TICK') {
            store.setPrice(payload.data as PriceUpdate);
=======
          if (payload.type === 'TICK') {
            setPrice(payload.data as PriceUpdate);
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
          } else if (payload.type === 'SIGNAL') {
            const signal = payload.data as TradeSignal;
            if (!signal.trading_style) signal.trading_style = 'Scalper';
            // Always update active signal AND add to history
<<<<<<< HEAD
            store.setActiveSignal(signal);
            store.addSignalToHistory(signal);
=======
            setActiveSignal(signal);
            addSignalToHistory(signal);
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
            
            // Show notification
            if (Notification.permission === 'granted') {
              new Notification(`Midas Signal: ${signal.direction}`, {
                body: `${signal.reasoning.substring(0, 80)}... (Confidence: ${signal.confidence}%)`,
                icon: '/favicon.ico',
              });
            }
            
            // Log to console for debugging
            console.log(`[Midas] New ${signal.trading_style} signal: ${signal.direction} @ ${signal.entry_price} (${signal.confidence}% confidence)`);
          }
        } catch {
          // Malformed message — ignore silently
        }
      };

      ws.onclose = (e) => {
        if (!mountedRef.current) return;
<<<<<<< HEAD
        useMidasStore.getState().setConnected(false);
=======
        setConnected(false);
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
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
<<<<<<< HEAD
  }, []); // No dependencies — WebSocket lifecycle is fully ref-based
=======
  }, [setPrice, setActiveSignal, addSignalToHistory, setConnected]);
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
};
