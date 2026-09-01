import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';

import { assertDiagnosis } from './contracts.mjs';
import { ScanStore } from './db.mjs';
import { buildDiagnosis } from './diagnosis.mjs';
import { GemmaClient } from './gemma.mjs';

const host = '127.0.0.1';
const port = Number(process.env.SPECCHECK_AGENT_PORT ?? 4318);
const projectRoot = resolve(import.meta.dirname, '..');
const dbPath = process.env.SPECCHECK_DB_PATH ?? resolve(projectRoot, 'data', 'speccheck.db');
const snapshotPath = process.env.SPECCHECK_SNAPSHOT_PATH ?? resolve(import.meta.dirname, 'data', 'sample-snapshot.json');
const schemaPath = resolve(projectRoot, 'schemas', 'diagnosis.schema.json');
const allowedOrigins = new Set((process.env.SPECCHECK_ALLOWED_ORIGINS ?? 'http://localhost:3000,http://127.0.0.1:3000').split(','));

const store = new ScanStore(dbPath);
const gemma = new GemmaClient();

function headers(request, contentType = 'application/json; charset=utf-8') {
  const origin = request.headers.origin;
  return {
    'content-type': contentType,
    'cache-control': 'no-store',
    'access-control-allow-origin': origin && allowedOrigins.has(origin) ? origin : 'http://localhost:3000',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type',
    vary: 'Origin',
  };
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
    if (size > 1_000_000) throw new Error('Request body exceeds 1 MB');
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

function validateSnapshot(snapshot) {
  if (!snapshot?.machine || !Array.isArray(snapshot.resources) || !Array.isArray(snapshot.findings)) {
    throw new TypeError('snapshot requires machine, resources, and findings');
  }
  if (!Array.isArray(snapshot.inventory) || !Array.isArray(snapshot.sources)) {
    throw new TypeError('snapshot requires inventory and sources');
  }
  return snapshot;
}

async function loadSnapshot() {
  return validateSnapshot(JSON.parse(await readFile(snapshotPath, 'utf8')));
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
  const url = new URL(request.url ?? '/', `http://${host}:${port}`);
  const origin = request.headers.origin;
  if (origin && !allowedOrigins.has(origin)) {
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
        agentVersion: '0.3.0',
        host,
        gemma: await gemma.status(),
      });
      return;
    }

    if (request.method === 'GET' && url.pathname === '/api/schema/diagnosis') {
      const schema = await readFile(schemaPath, 'utf8');
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
    const clientError = error instanceof SyntaxError || error instanceof TypeError || error.message.includes('1 MB');
    sendJson(response, request, clientError ? 400 : 500, {
      error: clientError ? 'invalid_request' : 'scan_failed',
      message: error.message,
    });
  }
});

server.listen(port, host, () => {
  console.log(`SpecCheck Local Agent listening on http://${host}:${port}`);
});

function shutdown() {
  server.close(() => {
    store.close();
    process.exit(0);
  });
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
