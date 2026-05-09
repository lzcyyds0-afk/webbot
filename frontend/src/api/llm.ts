import client from './client';
import type { LLMConfig, LLMConfigCreate, LLMConfigUpdate, LLMTestRequest, LLMTestResponse } from '../types';

export const fetchConfigs = () =>
  client.get<LLMConfig[]>('/llm/configs').then((r) => r.data);

export const createConfig = (data: LLMConfigCreate) =>
  client.post<LLMConfig>('/llm/configs', data).then((r) => r.data);

export const updateConfig = (id: number, data: LLMConfigUpdate) =>
  client.put<LLMConfig>(`/llm/configs/${id}`, data).then((r) => r.data);

export const deleteConfig = (id: number) =>
  client.delete(`/llm/configs/${id}`).then((r) => r.data);

export const testConfig = (data: LLMTestRequest) =>
  client.post<LLMTestResponse>('/llm/test', data).then((r) => r.data);