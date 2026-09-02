import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const projectRoot = resolve(import.meta.dirname, '..');
const packageMetadata = JSON.parse(readFileSync(resolve(projectRoot, 'package.json'), 'utf8'));

function positiveNumber(value, fallback, name) {
  const parsed = Number(value ?? fallback);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new TypeError(`${name} must be a positive number`);
  return parsed;
}

function projectPath(value, fallback) {
  return resolve(projectRoot, value ?? fallback);
}

const allowedOrigins = (process.env.SPECCHECK_ALLOWED_ORIGINS ?? 'http://localhost:3000,http://127.0.0.1:3000')
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean);

export const agentConfig = Object.freeze({
  version: packageMetadata.version,
  host: '127.0.0.1',
  port: positiveNumber(process.env.SPECCHECK_AGENT_PORT, 4318, 'SPECCHECK_AGENT_PORT'),
  dbPath: projectPath(process.env.SPECCHECK_DB_PATH, 'data/speccheck.db'),
  demoSnapshotPath: projectPath(process.env.SPECCHECK_SNAPSHOT_PATH, 'agent/fixtures/demo-snapshot.json'),
  schemaPath: resolve(projectRoot, 'schemas', 'diagnosis.schema.json'),
  allowedOrigins: new Set(allowedOrigins),
  requestBodyLimitBytes: positiveNumber(process.env.SPECCHECK_BODY_LIMIT_BYTES, 1_000_000, 'SPECCHECK_BODY_LIMIT_BYTES'),
});

export const gemmaConfig = Object.freeze({
  baseUrl: process.env.SPECCHECK_OLLAMA_URL ?? 'http://127.0.0.1:11434',
  model: process.env.SPECCHECK_GEMMA_MODEL ?? 'gemma3:4b',
  timeoutMs: positiveNumber(process.env.SPECCHECK_GEMMA_TIMEOUT_MS, 12_000, 'SPECCHECK_GEMMA_TIMEOUT_MS'),
  statusTimeoutMs: positiveNumber(process.env.SPECCHECK_GEMMA_STATUS_TIMEOUT_MS, 1_500, 'SPECCHECK_GEMMA_STATUS_TIMEOUT_MS'),
  temperature: Number(process.env.SPECCHECK_GEMMA_TEMPERATURE ?? 0.1),
  maxTokens: positiveNumber(process.env.SPECCHECK_GEMMA_MAX_TOKENS, 350, 'SPECCHECK_GEMMA_MAX_TOKENS'),
});
