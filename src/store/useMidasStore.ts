import { create } from 'zustand';
import type { TradeSignal } from '@/lib/types';

export type { TradeSignal };

export interface PriceUpdate {
  symbol: string;
  bid: number;
  ask: number;
  spread?: number;
  change?: number;
  changePercent?: number;
  high24h?: number;
  low24h?: number;
  time: string;
}

interface MidasState {
  currentPrice: PriceUpdate | null;
  activeSignal: TradeSignal | null;
  signalHistory: TradeSignal[];
  isConnected: boolean;

  setPrice: (price: PriceUpdate) => void;
  setActiveSignal: (signal: TradeSignal) => void;
  clearActiveSignal: () => void;
  addSignalToHistory: (signal: TradeSignal) => void;
  setConnected: (status: boolean) => void;
}

export const useMidasStore = create<MidasState>((set) => ({
  currentPrice: null,
  activeSignal: null,
  signalHistory: [],
  isConnected: false,

  setPrice: (price) => set({ currentPrice: price }),
  setActiveSignal: (signal) => set({ activeSignal: signal }),
  clearActiveSignal: () => set({ activeSignal: null }),
  addSignalToHistory: (signal) =>
    set((state) => {
      // Avoid exact duplicates (same entry_price + direction + timestamp)
      const key = `${signal.direction}-${signal.entry_price}-${signal.timestamp ?? ""}`;
      const exists = state.signalHistory.some(
        s => `${s.direction}-${s.entry_price}-${s.timestamp ?? ""}` === key
      );
      if (exists) return state;
      return { signalHistory: [signal, ...state.signalHistory].slice(0, 100) };
    }),
  setConnected: (status) => set({ isConnected: status }),
}));
