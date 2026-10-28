import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadScanResult, monitorScan } from '../app/scan-monitor.ts';

const state = (status, runId = 'existing-run') => ({
  runId, status, phase: status === 'running' ? 'collecting' : status,
  progress: status === 'running' ? 45 : 100, currentCollector: null,
  message: 'status', scanId: status === 'completed' ? 'result' : null,
  startedAt: null, finishedAt: null,
});

test('completion requests its exact result, not the latest result', async () => {
  const result = await loadScanResult(state('completed'), async (scanId) => {
    assert.equal(scanId, 'result');
    return { scanId };
  }, async () => state('completed'));
  assert.equal(result.diagnosis.scanId, 'result');
});

test('a newer run suppresses a late result from the previous run', async () => {
  for (const status of ['running', 'completed', 'failed']) {
    const result = await loadScanResult(state('completed'), async () => ({ scanId: 'result' }),
      async () => state(status, 'new-run'));
    assert.equal(result.diagnosis, null);
    assert.equal(result.current.runId, 'new-run');
  }
});

test('missing or mismatched result IDs never display another diagnosis', async () => {
  await assert.rejects(loadScanResult({ ...state('completed'), scanId: null },
    async () => assert.fail('must not fetch'), async () => state('completed')));
  await assert.rejects(loadScanResult(state('completed'), async () => ({ scanId: 'wrong' }),
    async () => state('completed')));
});

test('a new monitor resumes a server scan and finishes without starting another scan', async () => {
  const controller = new AbortController();
  const responses = [state('running'), state('completed')];
  const seen = [];
  await monitorScan({
    signal: controller.signal, intervalMs: 0,
    readStatus: async () => responses.shift(),
    onConnection: () => {}, onStatus: (status) => seen.push(status.status),
    onFinished: async (status) => {
      assert.equal(status.scanId, 'result');
      controller.abort();
    },
  });
  assert.deepEqual(seen, ['running', 'completed']);
});

test('connection loss preserves monitoring and resumes progress on reconnect', async () => {
  const controller = new AbortController();
  const connections = [];
  const seen = [];
  let reads = 0;
  await monitorScan({
    signal: controller.signal, intervalMs: 0,
    readStatus: async () => {
      reads++;
      if (reads === 2) throw new Error('offline');
      return state(reads === 3 ? 'completed' : 'running');
    },
    onConnection: (value) => connections.push(value),
    onStatus: (status) => seen.push(status.status),
    onFinished: async () => controller.abort(),
  });
  assert.deepEqual(connections, [true, false, true]);
  assert.deepEqual(seen, ['running', 'completed']);
});

test('terminal handling runs once per run and detects subsequent runs', async () => {
  const controller = new AbortController();
  const responses = [state('completed'), state('completed'), state('failed', 'next-run')];
  const finished = [];
  await monitorScan({
    signal: controller.signal, intervalMs: 0,
    readStatus: async () => responses.shift(),
    onConnection: () => {}, onStatus: () => {},
    onFinished: async (status) => {
      finished.push(status.runId);
      if (finished.length === 2) controller.abort();
    },
  });
  assert.deepEqual(finished, ['existing-run', 'next-run']);
});

test('failed result loading retries the completed run', async () => {
  const controller = new AbortController();
  let loads = 0;
  await monitorScan({
    signal: controller.signal, intervalMs: 0,
    readStatus: async () => state('completed'),
    onConnection: () => {}, onStatus: () => {},
    onFinished: async () => {
      if (++loads === 1) throw new Error('result unavailable');
      controller.abort();
    },
  });
  assert.equal(loads, 2);
});

test('unmount while a request is pending does not update the screen', async () => {
  const controller = new AbortController();
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  const monitoring = monitorScan({
    signal: controller.signal, intervalMs: 0, readStatus: () => pending,
    onStatus: () => assert.fail('update after unmount'),
    onConnection: () => assert.fail('update after unmount'),
    onFinished: async () => assert.fail('finish after unmount'),
  });
  controller.abort();
  release(state('running'));
  await monitoring;
});

test('result errors stop after three attempts without marking the service disconnected', async () => {
  const controller = new AbortController();
  const errors = [];
  let reads = 0;
  let loads = 0;
  await monitorScan({
    signal: controller.signal, intervalMs: 0,
    readStatus: async () => {
      if (++reads === 5) controller.abort();
      return state('completed');
    },
    onStatus: () => {},
    onConnection: (connected) => assert.equal(connected, true),
    onFinished: async () => { loads++; throw new Error('Gemma timeout'); },
    onResultError: (_error, status, attempt, willRetry) => {
      assert.equal(status.runId, 'existing-run');
      errors.push([attempt, willRetry]);
    },
  });
  assert.equal(loads, 3);
  assert.deepEqual(errors, [[1, true], [2, true], [3, false]]);
});

test('manual result retry creates a fresh budget without starting an Agent', async () => {
  for (let retry = 0; retry < 2; retry++) {
    const controller = new AbortController();
    let attempts = 0;
    await monitorScan({
      signal: controller.signal, intervalMs: 0,
      readStatus: async () => state('completed'),
      onConnection: () => {}, onStatus: () => {},
      onFinished: async () => { throw new Error('missing result'); },
      onResultError: (_error, _status, attempt, willRetry) => {
        attempts = attempt;
        if (!willRetry) controller.abort();
      },
    });
    assert.equal(attempts, 3);
  }
});

test('unmount suppresses late result errors', async () => {
  const controller = new AbortController();
  await monitorScan({
    signal: controller.signal, intervalMs: 0,
    readStatus: async () => state('completed'),
    onConnection: () => {}, onStatus: () => {},
    onFinished: async () => { controller.abort(); throw new Error('late'); },
    onResultError: () => assert.fail('error after unmount'),
  });
});
