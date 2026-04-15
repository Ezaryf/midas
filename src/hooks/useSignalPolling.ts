'use client';

import { startTransition } from 'react';
import { useEffect, useRef } from 'react';
import { useMidasStore, type PriceUpdate, type TradeSignal } from '@/store/useMidasStore';
import type { AnalysisBatch } from '@/lib/types';
import { getBackendUrl } from '@/lib/config';

const POLL_INTERVAL = 1000;

interface AccountResponse {
  connected: boolean;
  symbol?: string;
  bid?: number;
  ask?: number;
  spread?: number;
  time?: string;
}

export const useSignalPolling = () => {
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const isPollingRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;

    const poll = async () => {
      if (!mountedRef.current || isPollingRef.current) return;
      isPollingRef.current = true;

      try {
        // Poll account/price data
        const accountRes = await fetch(getBackendUrl('/api/account'), {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: AbortSignal.timeout(5000),
        });

        if (accountRes.ok) {
          const accountData: AccountResponse = await accountRes.json();
          
          if (accountData.connected && accountData.bid) {
            const priceUpdate: PriceUpdate = {
              symbol: accountData.symbol || 'XAUUSD',
              bid: accountData.bid,
              ask: accountData.ask || accountData.bid + (accountData.spread || 30) / 10000,
              spread: accountData.spread,
              time: accountData.time || new Date().toISOString(),
              source: 'http-poll',
            };
            
            startTransition(() => {
              useMidasStore.getState().setPrice(priceUpdate);
            });
          }
        }

        // Poll for signals/history to get latest signals
        const historyRes = await fetch(getBackendUrl('/api/history/signals?limit=5'), {
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
              store.setActiveSignal(latestSignal);
              store.addSignalToHistory(latestSignal);
            });
          }
        }

        // Poll for positions (to keep state fresh)
        const positionsRes = await fetch(getBackendUrl('/api/positions/open'), {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: AbortSignal.timeout(5000),
        });

        if (positionsRes.ok) {
          const positionsData: { positions?: unknown[] } = await positionsRes.json();
          // Positions are handled separately, just keep state updated
        }

      } catch (error) {
        // Silently ignore polling errors - we're using fallback
      } finally {
        isPollingRef.current = false;
      }
    };

    // Start polling
    poll(); // Initial poll
    intervalRef.current = setInterval(poll, POLL_INTERVAL);

    return () => {
      mountedRef.current = false;
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);
};
