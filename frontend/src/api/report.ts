import client from './client';
import type { ProjectReport } from '../types';

export const fetchProjectReport = (projectId: number, from?: string, to?: string) => {
  const params = new URLSearchParams();
  if (from) params.append('from', from);
  if (to) params.append('to', to);
  const qs = params.toString();
  return client
    .get<ProjectReport>(`/projects/${projectId}/report${qs ? '?' + qs : ''}`)
    .then((r) => r.data);
};
