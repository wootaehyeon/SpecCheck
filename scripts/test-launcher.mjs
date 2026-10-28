import assert from 'node:assert/strict';
import { test } from 'node:test';
import { inspectService, parsePort, serviceReady, waitForService } from './launcher-support.mjs';

test('ports are bounded integers', () => {
  assert.equal(parsePort(undefined, 3000), 3000);
  for (const value of ['abc', '3000x', '0', '65536', '-1']) assert.throws(() => parsePort(value, 3000));
});

test('reuse requires the exact project identity and healthy response', async () => {
  const response = (body) => async () => new Response(JSON.stringify(body));
  assert.equal(await serviceReady('url', 'ours', response({ status: 'ok', projectId: 'ours' })), true);
  assert.equal(await serviceReady('url', 'ours', response({ status: 'ok', projectId: 'other' })), false);
  assert.equal(await serviceReady('url', 'ours', response({ status: 'failed', projectId: 'ours' })), false);
  assert.equal(await serviceReady('url', 'ours', async () => { throw new Error('offline'); }), false);
});

test('reuse skips port allocation', async () => {
  assert.equal(await inspectService(3000, 'url', 'ours', {
    ready: async () => true, available: async () => assert.fail('must not bind'),
  }), 'reuse');
});

test('foreign or unresponsive port is rejected without stopping anything', async () => {
  await assert.rejects(inspectService(3000, 'url', 'ours', {
    ready: async () => false, available: async () => false,
  }), /No process was stopped/);
  assert.equal(await inspectService(3000, 'url', 'ours', {
    ready: async () => false, available: async () => true,
  }), 'start');
});

test('readiness waits for the server instead of opening an early browser', async () => {
  let probes = 0;
  await waitForService('url', 'ours', { ready: async () => ++probes === 3, intervalMs: 0 });
  assert.equal(probes, 3);
});

test('readiness times out or detects an early child exit', async () => {
  await assert.rejects(waitForService('url', 'ours', { ready: async () => false, timeoutMs: 5, intervalMs: 1 }), /did not become ready/);
  await assert.rejects(waitForService('url', 'ours', { failed: () => true }), /exited before readiness/);
});
