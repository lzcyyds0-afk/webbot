import { create } from 'zustand';
import type { LLMConfig, LLMConfigCreate, LLMConfigUpdate, LLMTestResponse } from '../types';
import * as llmApi from '../api/llm';

interface LLMState {
  configs: LLMConfig[];
  loading: boolean;
  testResult: LLMTestResponse | null;
  testing: boolean;

  fetchConfigs: () => Promise<void>;
  createConfig: (data: LLMConfigCreate) => Promise<void>;
  updateConfig: (id: number, data: LLMConfigUpdate) => Promise<void>;
  deleteConfig: (id: number) => Promise<void>;
  testConfig: (configId: number, prompt: string) => Promise<void>;
  clearTestResult: () => void;
}

export const useLLMStore = create<LLMState>((set, get) => ({
  configs: [],
  loading: false,
  testResult: null,
  testing: false,

  fetchConfigs: async () => {
    set({ loading: true });
    try {
      const configs = await llmApi.fetchConfigs();
      set({ configs });
    } finally {
      set({ loading: false });
    }
  },

  createConfig: async (data) => {
    await llmApi.createConfig(data);
    await get().fetchConfigs();
  },

  updateConfig: async (id, data) => {
    await llmApi.updateConfig(id, data);
    await get().fetchConfigs();
  },

  deleteConfig: async (id) => {
    await llmApi.deleteConfig(id);
    set({ configs: get().configs.filter((c) => c.id !== id) });
  },

  testConfig: async (configId, prompt) => {
    set({ testing: true, testResult: null });
    try {
      const result = await llmApi.testConfig({ config_id: configId, prompt });
      set({ testResult: result });
    } finally {
      set({ testing: false });
    }
  },

  clearTestResult: () => set({ testResult: null }),
}));