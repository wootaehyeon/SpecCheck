function positiveNumber(value: string | undefined, fallback: number) {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const diagnosticsConfig = Object.freeze({
  agentUrl: (process.env.NEXT_PUBLIC_SPECCHECK_AGENT_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, ''),
  requestTimeoutMs: positiveNumber(process.env.NEXT_PUBLIC_SPECCHECK_REQUEST_TIMEOUT_MS, 5_000),
  demoMode: process.env.NEXT_PUBLIC_SPECCHECK_DEMO_MODE === 'true',
});
