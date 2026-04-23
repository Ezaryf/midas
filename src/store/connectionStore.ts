// src/store/connectionStore.ts
import { create } from 'zustand';

interface ConnectionState {
  isWsConnected: boolean;
  backendOk: boolean;
  mt5Connected: boolean;
  aiProviderOk: boolean;
  alltickReady: boolean;
  lastPing: string | null;
  isReconnecting: boolean;

  setWsConnected: (connected: boolean) => void;
  setBackendOk: (ok: boolean) => void;
  setAiProviderOk: (ok: boolean) => void;
  setAlltickReady: (ready: boolean) => void;
  reconnectAll: () => Promise<void>;
}

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  isWsConnected: false,
  backendOk: false,
  mt5Connected: false,
  aiProviderOk: false,
  alltickReady: false,
  lastPing: null,
  isReconnecting: false,

  setWsConnected: (connected) => {
    set({ 
      isWsConnected: connected, 
      mt5Connected: connected 
    });
  },

  setBackendOk: (ok) => set({ backendOk: ok }),

  setAiProviderOk: (ok) => set({ aiProviderOk: ok }),

  setAlltickReady: (ready) => set({ alltickReady: ready }),

  reconnectAll: async () => {
    set({ isReconnecting: true });
    try {
      const res = await fetch('/api/reconnect', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const data = await res.json();
      if (data.status === 'ok') {
        set({ lastPing: new Date().toISOString() });
      }
    } catch (error) {
      console.error('Reconnect failed:', error);
    } finally {
      set({ isReconnecting: false });
    }
  },
}));