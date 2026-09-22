import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const packageManagerCli = process.env.npm_execpath;
if (!packageManagerCli) throw new Error('Run this command through pnpm or npm.');

const root = new URL('../', import.meta.url);
const backend = new URL('../backend/', import.meta.url);
const localPython = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
const python = process.env.SPECCHECK_PYTHON ?? (existsSync(localPython) ? localPython : process.platform === 'win32' ? 'python' : 'python3');
const backendPort = process.env.SPECCHECK_BACKEND_PORT ?? '8000';
const environment = {
  ...process.env,
  LOCAL_AGENT_BACKEND_URL: `http://127.0.0.1:${backendPort}`,
  NEXT_PUBLIC_SPECCHECK_AGENT_URL: `http://127.0.0.1:${backendPort}`,
};

function run(command, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, env: environment, stdio: 'inherit' });
    child.on('error', reject);
    child.on('exit', (code) => resolve(code ?? 1));
  });
}

// Vinext's Windows dev server can spin before replying to the first request.
// A production bundle is fast to create and is substantially more reliable for
// the user-facing one-click launcher.
const buildCode = await run(process.execPath, [packageManagerCli, 'build'], { cwd: root });
if (buildCode !== 0) process.exit(buildCode);

async function backendAlreadyRunning() {
  try {
    const response = await fetch(`http://127.0.0.1:${backendPort}/api/health`, { signal: AbortSignal.timeout(1500) });
    return response.ok;
  } catch {
    return false;
  }
}

const children = [];
if (await backendAlreadyRunning()) {
  console.log(`Reusing the existing SpecCheck backend on port ${backendPort}.`);
} else {
  children.push(spawn(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', backendPort], {
    cwd: backend,
    env: environment,
    stdio: 'inherit',
  }));
}
children.push(
  spawn(process.execPath, ['node_modules/wrangler/bin/wrangler.js', 'dev', '--config', 'dist/server/wrangler.json', '--port', '3000'], {
    cwd: root,
    env: environment,
    stdio: 'inherit',
  }),
);

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill('SIGTERM');
  setTimeout(() => process.exit(code), 250).unref();
}

for (const child of children) {
  child.on('error', () => stop(1));
  child.on('exit', (code) => {
    if (!stopping && code) stop(code);
  });
}

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
