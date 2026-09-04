import { diagnosticsConfig } from './config';
import type { AgentHealth, Diagnosis, LocalScanStatus, MarketPricesResponse } from './types';

type ErrorPayload = { error?: string; message?: string; detail?: string };

export class DiagnosticsApiError extends Error {
  constructor(message: string, readonly status: number, readonly code?: string) {
    super(message);
    this.name = 'DiagnosticsApiError';
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = diagnosticsConfig.requestTimeoutMs): Promise<T> {
  const response = await fetch(`${diagnosticsConfig.agentUrl}${path}`, {
    ...init,
    signal: AbortSignal.timeout(timeoutMs),
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

export function startBasicScan() {
  return request<LocalScanStatus>('/api/scans/start', {
    method: 'POST',
  });
}

export function getBasicScanStatus() {
  return request<LocalScanStatus>('/api/scans/status');
}

export function getMarketPrices(recommendations: Diagnosis['recommendations']) {
  const parts = recommendations.flatMap((recommendation) =>
    (recommendation.candidates ?? []).flatMap((candidate) =>
      candidate.parts.map((part) => ({
        key: part.key,
        category: part.category,
        name: part.searchQuery,
        userPrice: 0,
      })),
    ),
  );
  return request<MarketPricesResponse>('/api/market-prices', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      parts,
    }),
  }, 15_000);
}
