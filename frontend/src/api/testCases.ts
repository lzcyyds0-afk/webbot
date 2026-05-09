import client from './client';
import type { TestCase, TestCaseCreate, StepDef } from '../types';

export const fetchTestCases = (projectId: number) =>
  client.get<TestCase[]>(`/projects/${projectId}/test-cases`).then((r) => r.data);

export const fetchTestCase = (projectId: number, caseId: number) =>
  client.get<TestCase>(`/projects/${projectId}/test-cases/${caseId}`).then((r) => r.data);

export const createTestCase = (projectId: number, data: TestCaseCreate) =>
  client.post<TestCase>(`/projects/${projectId}/test-cases`, data).then((r) => r.data);

export const updateTestCaseSteps = (projectId: number, caseId: number, steps_json: StepDef[], cookies_json?: TestCase['cookies_json']) =>
  client.put<TestCase>(`/projects/${projectId}/test-cases/${caseId}`, { steps_json, cookies_json }).then((r) => r.data);

export const deleteTestCase = (projectId: number, caseId: number) =>
  client.delete(`/projects/${projectId}/test-cases/${caseId}`).then((r) => r.data);

// ── AI Generate ──

export interface GenerateRequest {
  project_id: number;
  url: string;
  goal: string;
  llm_config_id: number;
  cookies?: Array<{
    name: string;
    value: string;
    domain: string;
    path?: string;
    expires?: number;
    httpOnly?: boolean;
    secure?: boolean;
    sameSite?: 'Strict' | 'Lax' | 'None';
  }>;
  thorough?: boolean;
}

export interface GenerateResponse {
  steps: StepDef[];
  screenshot_b64?: string;
  elements_text?: string;
  raw_llm_output?: string;
  retry_used?: boolean;
}

export const generateSteps = (data: GenerateRequest) =>
  client.post<GenerateResponse>('/cases/generate', data).then((r) => r.data);

// ── AI Refine ──

export interface RefineRequest {
  steps: StepDef[];
  user_feedback: string;
  llm_config_id: number;
}

export interface RefineResponse {
  steps: StepDef[];
  raw_llm_output?: string;
}

export const refineSteps = (data: RefineRequest) =>
  client.post<RefineResponse>('/cases/refine', data).then((r) => r.data);
