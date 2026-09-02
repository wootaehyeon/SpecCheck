import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import { agentConfig } from './config.mjs';
import { assertDiagnosis, riskLevel } from './contracts.mjs';
import { ScanStore } from './db.mjs';
import { buildDiagnosis } from './diagnosis.mjs';
import { GemmaClient } from './gemma.mjs';
import { validateSnapshot } from './snapshot.mjs';

const snapshot = JSON.parse(await readFile(new URL('./fixtures/demo-snapshot.json', import.meta.url), 'utf8'));
const ai = {
  provider: 'template', model: 'test', status: 'fallback', overview: 'test overview', actionPlan: ['test action'],
};

test('risk level boundaries are stable', () => {
  assert.equal(riskLevel(0), 'low');
  assert.equal(riskLevel(40), 'medium');
  assert.equal(riskLevel(70), 'high');
  assert.equal(riskLevel(85), 'critical');
});

test('diagnosis assembly satisfies the runtime contract', () => {
  const diagnosis = buildDiagnosis(validateSnapshot(snapshot), { scanId: 'test-scan', generatedAt: '2026-09-01T00:00:00.000Z', ai });
  assert.equal(assertDiagnosis(diagnosis), diagnosis);
  assert.equal(diagnosis.categories.hardware.count, 1);
  assert.equal(diagnosis.risk.level, 'medium');
});

test('latest diagnosis is persisted in SQLite', () => {
  const store = new ScanStore(':memory:');
  const diagnosis = buildDiagnosis(snapshot, { scanId: 'sqlite-test', generatedAt: '2026-09-01T00:00:00.000Z', ai });
  store.save(diagnosis);
  assert.deepEqual(store.getLatest(), diagnosis);
  store.close();
});

test('Gemma integration rejects non-local endpoints', () => {
  assert.throws(() => new GemmaClient({ baseUrl: 'https://example.com' }), /loopback-only/);
});

test('agent version follows package metadata', async () => {
  const packageMetadata = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  assert.equal(agentConfig.version, packageMetadata.version);
});

test('snapshot boundary rejects incomplete collector payloads', () => {
  assert.throws(() => validateSnapshot({ machine: {}, resources: [] }), /findings must be an array/);
});
