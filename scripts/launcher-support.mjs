import { createServer } from 'node:net';

export function parsePort(value, fallback) {
  const text = String(value ?? fallback);
  if (!/^\d+$/.test(text) || Number(text) < 1 || Number(text) > 65535) throw new Error(`Invalid port: ${text}`);
  return Number(text);
}

export async function serviceReady(url, projectId, fetcher = fetch) {
  try {
    const response = await fetcher(url, { signal: AbortSignal.timeout(2000) });
    if (!response.ok) return false;
    const body = await response.json();
    return body.status === 'ok' && body.projectId === projectId;
  } catch { return false; }
}

export function portAvailable(port) {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', (error) => error.code === 'EADDRINUSE' ? resolve(false) : reject(error));
    server.listen(port, '127.0.0.1', () => server.close(() => resolve(true)));
  });
}

export async function inspectService(port, url, projectId, dependencies = {}) {
  const ready = dependencies.ready ?? serviceReady;
  const available = dependencies.available ?? portAvailable;
  if (await ready(url, projectId)) return 'reuse';
  if (!(await available(port))) throw new Error(`Port ${port} is occupied by an unverified or unresponsive server. Close it yourself or select another port. No process was stopped.`);
  return 'start';
}

export async function waitForService(url, projectId, { timeoutMs = 60000, ready = serviceReady, failed = () => false, intervalMs = 500 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (failed()) throw new Error(`Server exited before readiness: ${url}`);
    if (await ready(url, projectId)) return;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Server did not become ready within ${timeoutMs / 1000}s: ${url}`);
}
