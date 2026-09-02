import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';

import { agentConfig } from './config.mjs';
import { assertDiagnosis } from './contracts.mjs';
import { ScanStore } from './db.mjs';
import { buildDiagnosis } from './diagnosis.mjs';
import { GemmaClient } from './gemma.mjs';
import { validateSnapshot } from './snapshot.mjs';

const store = new ScanStore(agentConfig.dbPath);
const gemma = new GemmaClient();

function headers(request, contentType = 'application/json; charset=utf-8') {
  const origin = request.headers.origin;
  const responseHeaders = {
    'content-type': contentType,
    'cache-control': 'no-store',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type',
    vary: 'Origin',
  };
  if (origin && agentConfig.allowedOrigins.has(origin)) responseHeaders['access-control-allow-origin'] = origin;
  return responseHeaders;
}

function sendJson(response, request, status, value) {
  response.writeHead(status, headers(request));
  response.end(JSON.stringify(value));
}

async function readJsonBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > agentConfig.requestBodyLimitBytes) throw new Error('Request body exceeds configured limit');
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

async function loadSnapshot() {
  return validateSnapshot(JSON.parse(await readFile(agentConfig.demoSnapshotPath, 'utf8')));
}

async function runBasicScan(snapshot) {
  const generatedAt = new Date().toISOString();
  const seed = buildDiagnosis(snapshot, {
    scanId: randomUUID(),
    generatedAt,
    ai: {
      provider: 'template',
      model: 'deterministic-ko-v1',
      status: 'unavailable',
      overview: '진단 설명을 준비 중입니다.',
      actionPlan: ['진단 결과를 확인하세요.'],
    },
  });
  const diagnosis = { ...seed, ai: await gemma.explain(seed) };
  assertDiagnosis(diagnosis);
  store.save(diagnosis);
  return diagnosis;
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? '/', `http://${agentConfig.host}:${agentConfig.port}`);
  const origin = request.headers.origin;
  if (origin && !agentConfig.allowedOrigins.has(origin)) {
    sendJson(response, request, 403, { error: 'origin_not_allowed' });
    return;
  }

  if (request.method === 'OPTIONS') {
    response.writeHead(204, headers(request));
    response.end();
    return;
  }

  try {
    if (request.method === 'GET' && url.pathname === '/api/health') {
      sendJson(response, request, 200, {
        status: 'ok',
        agentVersion: agentConfig.version,
        host: agentConfig.host,
        gemma: await gemma.status(),
      });
      return;
    }

    if (request.method === 'GET' && url.pathname === '/api/schema/diagnosis') {
      const schema = await readFile(agentConfig.schemaPath, 'utf8');
      response.writeHead(200, headers(request, 'application/schema+json; charset=utf-8'));
      response.end(schema);
      return;
    }

    if (request.method === 'GET' && url.pathname === '/api/scans/latest') {
      const latest = store.getLatest();
      sendJson(response, request, latest ? 200 : 404, latest ?? { error: 'scan_not_found' });
      return;
    }

    if (request.method === 'POST' && url.pathname === '/api/scans') {
      const body = await readJsonBody(request);
      const snapshot = body.snapshot ? validateSnapshot(body.snapshot) : await loadSnapshot();
      sendJson(response, request, 201, await runBasicScan(snapshot));
      return;
    }

    sendJson(response, request, 404, { error: 'route_not_found' });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown scan error';
    const clientError = error instanceof SyntaxError || error instanceof TypeError || message.includes('configured limit');
    sendJson(response, request, clientError ? 400 : 500, {
      error: clientError ? 'invalid_request' : 'scan_failed',
      message,
    });
  }
});

server.listen(agentConfig.port, agentConfig.host, () => {
  console.log(`SpecCheck Local Agent listening on http://${agentConfig.host}:${agentConfig.port}`);
});

function shutdown() {
  server.close(() => {
    store.close();
    process.exit(0);
  });
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
