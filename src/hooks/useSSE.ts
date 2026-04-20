'use client';

import { useEffect, useRef } from 'react';
import { useMidasStore, type PriceUpdate, type TradeSignal } from '@/store/useMidasStore';
import type { AnalysisBatch, EngineStatus, ExecutionAck } from '@/lib/types';
import { getBackendUrl } from '@/lib/config';

const SSE_URL = '/api/sse/stream';
const SSE_URL_FULL = 'http://127.0.0.1:8000/api/sse/stream';

export const useSSE = () => {
  const eventSourceRef = useRef<EventSource | null>(null);
  const mountedRef = useRef(true);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;

    const connect = () => {
      if (!mountedRef.current) return;
      
      // Try full URL first (more reliable for SSE)
      const url = SSE_URL_FULL;
      console.log(`[SSE] Connecting to ${url}`);
      
      try {
        const eventSource = new EventSource(url);
        eventSourceRef.current = eventSource;

        eventSource.onopen = () => {
          if (!mountedRef.current) return;
          console.log('[SSE] Connected');
        };

        eventSource.onmessage = (event) => {
          if (!mountedRef.current) return;
          try {
            const payload = JSON.parse(event.data);
            const store = useMidasStore.getState();
            
            if (payload.type === 'TICK') {
              const tickData = payload.data as PriceUpdate;
              tickData.source = 'sse';
              store.setPrice(tickData);
              console.log('[SSE] Tick received:', tickData.bid);
            } else if (payload.type === 'SIGNAL') {
              const signal = payload.data as TradeSignal;
              if (!signal.trading_style) signal.trading_style = 'Scalper';
              store.setActiveSignal(signal);
              store.addSignalToHistory(signal);
              console.log(`[SSE] Signal: ${signal.direction} @ ${signal.entry_price}`);
            } else if (payload.type === 'SIGNAL_BATCH') {
              const batch = payload.data as AnalysisBatch;
              if (batch?.primary) {
                store.setAnalysisBatch(batch);
                store.addSignalToHistory(batch.primary);
                batch.backups?.forEach((backup) => store.addSignalToHistory(backup));
              }
            } else if (payload.type === 'MARKET_STATE') {
              store.setMarketState(payload.data);
            } else if (payload.type === 'ENGINE_STATUS') {
              const status = payload.data as EngineStatus;
              if (status?.phase && status?.message) {
                store.setEngineStatus(status);
              }
            } else if (payload.type === 'EXECUTION_ACK') {
              store.setExecutionAck(payload.data as ExecutionAck);
            }
          } catch (e) {
            // Silently ignore parse errors
          }
        };

        eventSource.onerror = (error) => {
          console.error('[SSE] Error:', {
            readyState: eventSource.readyState,
            url: url,
            error: error
          });
          eventSource.close();
          
          // Manual reconnection - SSE has auto-reconnect but we'll control it
          if (mountedRef.current) {
            console.log('[SSE] Reconnecting in 5s...');
            reconnectTimeoutRef.current = setTimeout(connect, 5000);
          }
        };
      } catch (e) {
        console.error('[SSE] Failed to create EventSource:', e);
        if (mountedRef.current) {
          reconnectTimeoutRef.current = setTimeout(connect, 5000);
        }
      }
    };

    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);
};
