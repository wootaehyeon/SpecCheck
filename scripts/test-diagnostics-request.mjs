import assert from 'node:assert/strict';
import { test } from 'node:test';
import { requestJson } from '../app/diagnostics-request.ts';

test('network failure is distinct from timeout', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('offline'); });
  await assert.rejects(requestJson('http://localhost/test', undefined, 100), { code: 'NETWORK_ERROR' });
});

test('timeout while waiting for headers is actionable', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new DOMException('timeout', 'TimeoutError'); });
  await assert.rejects(requestJson('http://localhost/test', undefined, 100), { code: 'REQUEST_TIMEOUT' });
});

test('timeout reading the response body is not swallowed', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({
    ok: true, status: 200,
    json: async () => { throw new DOMException('timeout', 'TimeoutError'); },
  }));
  // Emulate an already expired body-read signal as real fetch would do.
  t.mock.method(AbortSignal, 'timeout', () => AbortSignal.abort());
  await assert.rejects(requestJson('http://localhost/test', undefined, 100), { code: 'REQUEST_TIMEOUT' });
});

test('HTTP failure preserves server error code and message', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    error: 'SCAN_CLEANUP_REQUIRED', message: 'Agent 종료 확인 필요',
  }), { status: 409 }));
  await assert.rejects(requestJson('http://localhost/test', undefined, 100), {
    status: 409, code: 'SCAN_CLEANUP_REQUIRED', message: 'Agent 종료 확인 필요',
  });
});

test('malformed success payload is rejected rather than treated as a diagnosis', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<html>error</html>'));
  await assert.rejects(requestJson('http://localhost/test', undefined, 100), { code: 'INVALID_RESPONSE' });
});

test('structured input validation errors display readable messages', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    detail: [{ msg: 'Price must be positive' }, { msg: 'An eBay item URL is required' }],
  }), { status: 422 }));
  await assert.rejects(requestJson('http://localhost/test', undefined, 100), {
    status: 422, message: 'Price must be positive; An eBay item URL is required',
  });
});
