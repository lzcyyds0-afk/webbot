import client from './client';
import type { TestCaseExplainOut } from '../types';

export const explainTestCase = (projectId: number, caseId: number) => {
  return client
    .post<TestCaseExplainOut>(`/projects/${projectId}/test-cases/${caseId}/explain`)
    .then((r) => r.data);
};
