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
<<<<<<< HEAD
  targetSymbol: string;
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1

  setPrice: (price: PriceUpdate) => void;
  setActiveSignal: (signal: TradeSignal) => void;
  clearActiveSignal: () => void;
  addSignalToHistory: (signal: TradeSignal) => void;
  setConnected: (status: boolean) => void;
<<<<<<< HEAD
  setTargetSymbol: (symbol: string) => void;
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
}

export const useMidasStore = create<MidasState>((set) => ({
  currentPrice: null,
  activeSignal: null,
  signalHistory: [],
  isConnected: false,
<<<<<<< HEAD
  targetSymbol: "XAUUSD",
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1

  setPrice: (price) => set({ currentPrice: price }),
  setActiveSignal: (signal) => set({ activeSignal: signal }),
  clearActiveSignal: () => set({ activeSignal: null }),
  addSignalToHistory: (signal) =>
    set((state) => {
<<<<<<< HEAD
      // Avoid exact duplicates (same entry_price + direction + symbol)
      const symbol = signal.symbol || state.targetSymbol;
      const key = `${symbol}-${signal.direction}-${signal.entry_price}`;
      const exists = state.signalHistory.some(
        s => `${s.symbol || state.targetSymbol}-${s.direction}-${s.entry_price}` === key
=======
      // Avoid exact duplicates (same entry_price + direction + timestamp)
      const key = `${signal.direction}-${signal.entry_price}-${signal.timestamp ?? ""}`;
      const exists = state.signalHistory.some(
        s => `${s.direction}-${s.entry_price}-${s.timestamp ?? ""}` === key
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
      );
      if (exists) return state;
      return { signalHistory: [signal, ...state.signalHistory].slice(0, 100) };
    }),
  setConnected: (status) => set({ isConnected: status }),
<<<<<<< HEAD
  setTargetSymbol: (symbol) => set({ targetSymbol: symbol }),
=======
>>>>>>> 43c9f1b194f748ead11d6ed556a8f6ef5941c6e1
}));
