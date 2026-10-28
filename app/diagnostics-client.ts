import { diagnosticsConfig } from './config';
import type { AgentHealth, Diagnosis, LocalScanStatus, MarketPricesResponse } from './types';
import { DiagnosticsApiError, requestJson } from './diagnostics-request';
export { DiagnosticsApiError } from './diagnostics-request';

async function request<T>(path: string, init?: RequestInit, timeoutMs = diagnosticsConfig.requestTimeoutMs): Promise<T> {
  return requestJson<T>(`${diagnosticsConfig.agentUrl}${path}`, init, timeoutMs);
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

export function getDiagnosis(scanId: string) {
  return request<Diagnosis>(`/api/scans/${encodeURIComponent(scanId)}`);
}

export function getBasicScanStatus() {
  return request<LocalScanStatus>('/api/scans/status', undefined, 5_000);
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
