'use client';

import { startTransition } from 'react';
import { useEffect, useRef } from 'react';
import { useMidasStore, type PriceUpdate, type TradeSignal } from '@/store/useMidasStore';

const BASE_POLL_INTERVAL = 3000;
const MAX_POLL_INTERVAL = 15000;

interface AccountResponse {
  connected: boolean;
  symbol?: string;
  bid?: number;
  ask?: number;
  spread?: number;
  time?: string;
  received_at?: string;
}

export const useSignalPolling = () => {
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const isPollingRef = useRef(false);
  const errorCountRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;

    const poll = async () => {
      if (!mountedRef.current || isPollingRef.current) return;
      if (useMidasStore.getState().isConnected) {
        scheduleNext(BASE_POLL_INTERVAL);
        return;
      }
      isPollingRef.current = true;
      let hadError = false;

      try {
        const accountRes = await fetch('/api/backend/health', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: AbortSignal.timeout(5000),
        });

        if (accountRes.ok) {
          const accountData = await accountRes.json();
          const tick = accountData?.runtime_state?.latest_tick as AccountResponse | undefined;
          
          if (accountData.mt5_connected && tick?.bid) {
            const priceUpdate: PriceUpdate = {
              symbol: tick.symbol || 'XAUUSD',
              bid: tick.bid,
              ask: tick.ask || tick.bid + (tick.spread || 30) / 10000,
              spread: tick.spread,
              time: tick.time || new Date().toISOString(),
              received_at: tick.received_at,
              source: 'http-poll',
            };
            
            startTransition(() => {
              useMidasStore.getState().setPrice(priceUpdate);
            });
          }
        } else {
          hadError = true;
        }

        const historyRes = await fetch('/api/signals/history', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: AbortSignal.timeout(5000),
        });

        if (historyRes.ok) {
          const historyData: { signals?: TradeSignal[] } = await historyRes.json();
          if (historyData.signals && historyData.signals.length > 0) {
            const latestSignal = historyData.signals[0];
            startTransition(() => {
              const store = useMidasStore.getState();
              const key =
                latestSignal.id ||
                latestSignal.signal_id ||
                (latestSignal.analysis_batch_id
                  ? `${latestSignal.analysis_batch_id}-${latestSignal.rank ?? 1}`
                  : `${latestSignal.symbol || store.targetSymbol}-${latestSignal.direction}-${latestSignal.entry_price}`);
              const existing = store.signalHistory.find((signal) => {
                const existingKey =
                  signal.id ||
                  signal.signal_id ||
                  (signal.analysis_batch_id
                    ? `${signal.analysis_batch_id}-${signal.rank ?? 1}`
                    : `${signal.symbol || store.targetSymbol}-${signal.direction}-${signal.entry_price}`);
                return existingKey === key;
              });
              const terminal = ["HIT_TP1", "HIT_TP2", "STOPPED", "EXPIRED"].includes(existing?.status || latestSignal.status || "");
              if (!terminal) store.setActiveSignal(latestSignal);
              store.addSignalToHistory(latestSignal);
            });
          }
        } else {
          hadError = true;
        }

        const positionsRes = await fetch('/api/positions', {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: AbortSignal.timeout(5000),
        });

        if (positionsRes.ok) {
          const positionsData: { positions?: unknown[] } = await positionsRes.json();
          // Positions are handled separately, just keep state updated
        } else {
          hadError = true;
        }

      } catch (error) {
        hadError = true;
      } finally {
        errorCountRef.current = hadError ? Math.min(errorCountRef.current + 1, 4) : 0;
        isPollingRef.current = false;
        scheduleNext(Math.min(BASE_POLL_INTERVAL * 2 ** errorCountRef.current, MAX_POLL_INTERVAL));
      }
    };

    const scheduleNext = (delay: number) => {
      if (!mountedRef.current) return;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(poll, delay);
    };

    poll(); // Initial poll

    return () => {
      mountedRef.current = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);
};
