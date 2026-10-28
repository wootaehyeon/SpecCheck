function positiveNumber(value: string | undefined, fallback: number) {
  const parsed = Number(value ?? fallback);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const diagnosticsConfig = Object.freeze({
  agentUrl: (process.env.NEXT_PUBLIC_SPECCHECK_AGENT_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, ''),
  // A cold local Gemma model can take tens of seconds to produce the first
  // explanation. Keep normal API calls local, but do not turn that expected
  // warm-up into a misleading browser timeout.
  requestTimeoutMs: positiveNumber(process.env.NEXT_PUBLIC_SPECCHECK_REQUEST_TIMEOUT_MS, 90_000),
  demoMode: process.env.NEXT_PUBLIC_SPECCHECK_DEMO_MODE === 'true',
});
