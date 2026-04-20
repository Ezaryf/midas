import { create } from 'zustand';
import type { AnalysisBatch, EngineStatus, ExecutionAck, TradeSignal, MarketState } from '@/lib/types';
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
  received_at?: string;
  source_received_at?: string;
  source?: string;
}

interface MidasState {
  currentPrice: PriceUpdate | null;
  activeSignal: TradeSignal | null;
  latestBatch: AnalysisBatch | null;
  marketState: MarketState | null;
  engineStatus: EngineStatus | null;
  engineLog: EngineStatus[];
  executionAck: ExecutionAck | null;
  executionLog: ExecutionAck[];
  signalHistory: TradeSignal[];
  isConnected: boolean;
  targetSymbol: string;
  calibrationFactor: number;

  setPrice: (price: PriceUpdate) => void;
  setCalibrationFactor: (factor: number) => void;
  setActiveSignal: (signal: TradeSignal) => void;
  setAnalysisBatch: (batch: AnalysisBatch) => void;
  setMarketState: (state: MarketState) => void;
  setEngineStatus: (status: EngineStatus) => void;
  setExecutionAck: (ack: ExecutionAck) => void;
  updateSignalStatus: (key: string, status: TradeSignal["status"]) => void;
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
  engineStatus: null,
  engineLog: [],
  executionAck: null,
  executionLog: [],
  signalHistory: [],
  isConnected: false,
  targetSymbol: DEFAULT_SYMBOL,
  calibrationFactor: DEFAULT_CALIBRATION_FACTOR,

  setPrice: (price) => set({ currentPrice: price }),
  setCalibrationFactor: (factor) => set({ calibrationFactor: factor }),
  setActiveSignal: (signal) => set({ activeSignal: signal }),
  setAnalysisBatch: (batch) => set({ latestBatch: batch, activeSignal: batch.primary }),
  setMarketState: (ms) => set({ marketState: ms }),
  setEngineStatus: (status) =>
    set((state) => {
      const last = state.engineLog[0];
      const isDuplicate =
        last?.phase === status.phase &&
        last?.message === status.message &&
        last?.detail === status.detail &&
        last?.updated_at === status.updated_at;
      return {
        engineStatus: status,
        engineLog: isDuplicate ? state.engineLog : [status, ...state.engineLog].slice(0, 30),
      };
    }),
  setExecutionAck: (ack) =>
    set((state) => {
      const enriched = { ...ack, updated_at: ack.updated_at || new Date().toISOString() };
      const last = state.executionLog[0];
      const isDuplicate =
        last?.signal_id === enriched.signal_id &&
        last?.status === enriched.status &&
        last?.message === enriched.message &&
        last?.ticket === enriched.ticket;
      return {
        executionAck: enriched,
        executionLog: isDuplicate ? state.executionLog : [enriched, ...state.executionLog].slice(0, 20),
      };
    }),
  updateSignalStatus: (key, status) =>
    set((state) => {
      const signalKey = (signal: TradeSignal) =>
        signal.id ||
        signal.signal_id ||
        (signal.analysis_batch_id
          ? `${signal.analysis_batch_id}-${signal.rank ?? 1}`
          : `${signal.symbol || state.targetSymbol}-${signal.direction}-${signal.entry_price}`);
      const update = (signal: TradeSignal) =>
        signalKey(signal) === key ? { ...signal, status } : signal;
      return {
        activeSignal:
          state.activeSignal && signalKey(state.activeSignal) === key
            ? { ...state.activeSignal, status }
            : state.activeSignal,
        signalHistory: state.signalHistory.map(update),
      };
    }),
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
