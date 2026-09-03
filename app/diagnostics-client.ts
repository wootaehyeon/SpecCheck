import { diagnosticsConfig } from './config';
import type { AgentHealth, Diagnosis } from './types';

type ErrorPayload = { error?: string; message?: string; detail?: string };

export class DiagnosticsApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = 'DiagnosticsApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${diagnosticsConfig.agentUrl}${path}`, {
    ...init,
    signal: AbortSignal.timeout(diagnosticsConfig.requestTimeoutMs),
  });
  const payload = await response.json().catch(() => ({})) as T & ErrorPayload;
  if (!response.ok) {
    throw new DiagnosticsApiError(payload.message ?? payload.detail ?? 'SpecCheck Backend 요청에 실패했습니다.', response.status, payload.error);
  }
  return payload;
}

export function getAgentHealth() {
  return request<AgentHealth>('/api/health');
}

export async function getLatestDiagnosis() {
  try {
    return await request<Diagnosis>('/api/scans/latest');
  } catch (error) {
    if (error instanceof DiagnosticsApiError && error.status === 404) return null;
    throw error;
  }
}

export function runBasicScan(snapshot?: unknown) {
  return request<Diagnosis>('/api/scans', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(snapshot === undefined ? {} : { snapshot }),
  });
}
