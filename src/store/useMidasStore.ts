import { create } from 'zustand';
import type { AnalysisBatch, TradeSignal, MarketState } from '@/lib/types';
import { DEFAULT_SYMBOL, DEFAULT_CALIBRATION_FACTOR, MAX_SIGNAL_HISTORY } from '@/lib/constants';

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
  source?: string;
}

interface MidasState {
  currentPrice: PriceUpdate | null;
  activeSignal: TradeSignal | null;
  latestBatch: AnalysisBatch | null;
  marketState: MarketState | null;
  signalHistory: TradeSignal[];
  isConnected: boolean;
  targetSymbol: string;
  calibrationFactor: number;

  setPrice: (price: PriceUpdate) => void;
  setCalibrationFactor: (factor: number) => void;
  setActiveSignal: (signal: TradeSignal) => void;
  setAnalysisBatch: (batch: AnalysisBatch) => void;
  setMarketState: (state: MarketState) => void;
  clearActiveSignal: () => void;
  addSignalToHistory: (signal: TradeSignal) => void;
  setConnected: (status: boolean) => void;
  setTargetSymbol: (symbol: string) => void;
}

export const useMidasStore = create<MidasState>((set) => ({
  currentPrice: null,
  activeSignal: null,
  latestBatch: null,
  marketState: null,
  signalHistory: [],
  isConnected: false,
  targetSymbol: DEFAULT_SYMBOL,
  calibrationFactor: DEFAULT_CALIBRATION_FACTOR,

  setPrice: (price) => set({ currentPrice: price }),
  setCalibrationFactor: (factor) => set({ calibrationFactor: factor }),
  setActiveSignal: (signal) => set({ activeSignal: signal }),
  setAnalysisBatch: (batch) => set({ latestBatch: batch, activeSignal: batch.primary }),
  setMarketState: (ms) => set({ marketState: ms }),
  clearActiveSignal: () => set({ activeSignal: null }),
  addSignalToHistory: (signal) =>
    set((state) => {
      const symbol = signal.symbol || state.targetSymbol;
      const key =
        signal.id ||
        signal.signal_id ||
        (signal.analysis_batch_id
          ? `${signal.analysis_batch_id}-${signal.rank ?? 1}`
          : `${symbol}-${signal.direction}-${signal.entry_price}`);
      const exists = state.signalHistory.some(
        (s) =>
          (s.id ||
            s.signal_id ||
            (s.analysis_batch_id
              ? `${s.analysis_batch_id}-${s.rank ?? 1}`
              : `${s.symbol || state.targetSymbol}-${s.direction}-${s.entry_price}`)) === key
      );
      if (exists) return state;
      return { signalHistory: [signal, ...state.signalHistory].slice(0, MAX_SIGNAL_HISTORY) };
    }),
  setConnected: (status) => set({ isConnected: status }),
  setTargetSymbol: (symbol) => set({ targetSymbol: symbol }),
}));
