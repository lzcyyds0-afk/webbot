import client from './client';
import type { Run, RunCreate, RunStep, StepDetails, StepDiagnosis } from '../types';

export interface ExportRunResponse {
  download_url: string;
  filename: string;
  expires_at: string;
}

export const createRun = (data: RunCreate) =>
  client.post<Run>('/runs', data).then((r) => r.data);

export const exportRun = (runId: number, format: 'html' | 'pdf' = 'html') =>
  client.post<ExportRunResponse>(`/runs/${runId}/export`, { format }).then((r) => r.data);

export const fetchRun = (id: number) =>
  client.get<Run>(`/runs/${id}`).then((r) => r.data);

export const fetchRunSteps = (runId: number) =>
  client.get<RunStep[]>(`/runs/${runId}/steps`).then((r) => r.data);

export const fetchStepDetails = (runId: number, stepIndex: number) =>
  client.get<StepDetails>(`/runs/${runId}/steps/${stepIndex}/details`).then((r) => r.data);

export const fetchStepDiagnosis = (runId: number, stepIndex: number) =>
  // A 404 here just means "no diagnosis yet" — a normal state, so don't toast.
  client
    .get<StepDiagnosis>(`/runs/${runId}/steps/${stepIndex}/diagnosis`, { skipErrorToast: true })
    .then((r) => r.data);

export const runAiDiagnosis = (runId: number, stepIndex: number, llmConfigId?: number) =>
  client.post<StepDiagnosis>(`/runs/${runId}/steps/${stepIndex}/ai-diagnose`, { llm_config_id: llmConfigId }).then((r) => r.data);
