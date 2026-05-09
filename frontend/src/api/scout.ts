import client from './client';
import type { ScoutResponse } from '../types';

export interface ScoutRequest {
  url: string;
  goal?: string;
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
}

export const scoutPage = (data: ScoutRequest) =>
  client.post<ScoutResponse>('/scout', data).then((r) => r.data);
