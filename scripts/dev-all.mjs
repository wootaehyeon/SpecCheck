import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const packageManagerCli = process.env.npm_execpath;
if (!packageManagerCli) throw new Error('Run this command through pnpm or npm.');
const localPython = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
const python = process.env.SPECCHECK_PYTHON ?? (existsSync(localPython) ? localPython : process.platform === 'win32' ? 'python' : 'python3');
const backendPort = process.env.SPECCHECK_BACKEND_PORT ?? '8000';
const backendUrl = `http://127.0.0.1:${backendPort}`;
const environment = {
  ...process.env,
  LOCAL_AGENT_BACKEND_URL: backendUrl,
  NEXT_PUBLIC_SPECCHECK_AGENT_URL: backendUrl,
};

const children = [
  spawn(python, ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', backendPort], {
    cwd: new URL('../backend/', import.meta.url),
    env: environment,
    stdio: 'inherit',
  }),
  spawn(process.execPath, [packageManagerCli, 'dev'], { env: environment, stdio: 'inherit' }),
];

let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill('SIGTERM');
  setTimeout(() => process.exit(code), 250).unref();
}

for (const child of children) {
  child.on('error', (error) => {
    console.error(error.message);
    stop(1);
  });
  child.on('exit', (code) => {
    if (!stopping && code) stop(code);
  });
}

process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
