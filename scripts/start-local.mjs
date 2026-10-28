import { spawn } from 'node:child_process';
import { existsSync, realpathSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { inspectService, parsePort, waitForService } from './launcher-support.mjs';

const root = realpathSync(fileURLToPath(new URL('../', import.meta.url)));
const projectId = createHash('sha256').update(root.replaceAll('\\', '/').toLowerCase()).digest('hex').slice(0, 16);
const localPython = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
const python = process.env.SPECCHECK_PYTHON ?? (existsSync(localPython) ? localPython : process.platform === 'win32' ? 'python' : 'python3');
const children = new Set();
let stopping = false;
let ready = false;

async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  await Promise.all([...children].map((child) => new Promise((resolve) => {
    if (!child.pid || child.exitCode !== null || child.signalCode !== null) return resolve();
    child.once('exit', resolve);
    const timeout = setTimeout(() => {
      console.error(`Could not confirm shutdown of owned process ${child.pid}. Check it before relaunching.`);
      resolve();
    }, 5000);
    timeout.unref();
    child.once('exit', () => clearTimeout(timeout));
    if (process.platform === 'win32') {
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
      killer.on('exit', (code) => {
        if (code) console.error(`Cleanup command failed for owned process ${child.pid} (${code}).`);
      });
      killer.on('error', () => { child.kill(); });
    } else child.kill('SIGTERM');
  })));
  process.exit(code);
}

function start(command, args, cwd, env) {
  const child = spawn(command, args, { cwd, env, stdio: 'inherit', windowsHide: true });
  children.add(child);
  child.on('error', (error) => {
    child.launchError = error;
    console.error(error.message);
    if (ready && !stopping) void stop(1);
  });
  child.on('exit', (code) => {
    children.delete(child);
    if (ready && !stopping) {
      console.error(`A managed server exited unexpectedly (${code}).`);
      void stop(1);
    }
  });
  return child;
}

function exited(child) {
  return Boolean(child.launchError || child.exitCode !== null || child.signalCode !== null);
}

process.once('SIGINT', () => void stop(0));
process.once('SIGTERM', () => void stop(0));

try {
  const backendPort = parsePort(process.env.SPECCHECK_BACKEND_PORT, 8000);
  const uiPort = parsePort(process.env.SPECCHECK_UI_PORT, 3000);
  if (backendPort === uiPort) throw new Error('Backend and UI ports must differ.');
  const backendUrl = `http://127.0.0.1:${backendPort}`;
  const uiUrl = `http://127.0.0.1:${uiPort}`;
  const backendHealth = `${backendUrl}/health`;
  const uiHealth = `${uiUrl}/api/local-status`;
  const env = {
    ...process.env,
    SPECCHECK_SIMPLE_DEV: '1',
    SPECCHECK_PROJECT_ID: projectId,
    LOCAL_AGENT_BACKEND_URL: backendUrl,
    NEXT_PUBLIC_SPECCHECK_AGENT_URL: backendUrl,
    CORS_ORIGINS: [uiUrl, `http://localhost:${uiPort}`, `http://[::1]:${uiPort}`].join(','),
  };
  const backendMode = await inspectService(backendPort, backendHealth, projectId);
  const uiMode = await inspectService(uiPort, uiHealth, projectId);
  if (backendMode === 'reuse') {
    const body = await (await fetch(backendHealth, { signal: AbortSignal.timeout(2000) })).json();
    if (!body.corsOrigins?.includes(uiUrl) || body.localAgentBackendUrl !== backendUrl) {
      throw new Error('Existing backend has incompatible CORS or Agent upload settings. Stop it before changing ports.');
    }
  }
  if (uiMode === 'reuse') {
    const body = await (await fetch(uiHealth, { signal: AbortSignal.timeout(2000) })).json();
    if (body.backendUrl !== backendUrl) throw new Error('Existing UI uses a different backend URL. Stop it before changing ports.');
  } else {
    const build = start(process.execPath, ['node_modules/vinext/dist/cli.js', 'build'], root, env);
    const code = await new Promise((resolve, reject) => {
      build.once('error', reject);
      build.once('exit', (code) => resolve(code));
    });
    if (code !== 0) throw new Error(`UI build failed (${code}).`);
  }
  let backendChild;
  if (backendMode === 'start') backendChild = start(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)], new URL('../backend/', import.meta.url), env);
  else console.log('Reusing this project\'s backend.');
  await waitForService(backendHealth, projectId, { failed: () => backendChild && exited(backendChild) });
  let uiChild;
  if (uiMode === 'start') uiChild = start(process.execPath, ['node_modules/vinext/dist/cli.js', 'start', '--hostname', '127.0.0.1', '--port', String(uiPort)], root, env);
  else console.log('Reusing this project\'s UI.');
  await waitForService(uiHealth, projectId, { failed: () => (uiChild && exited(uiChild)) || (backendChild && exited(backendChild)) });
  const page = await fetch(uiUrl, { signal: AbortSignal.timeout(10000) });
  if (!page.ok || !(await page.text()).includes('SpecCheck')) throw new Error('UI page did not render SpecCheck.');
  ready = true;
  console.log(`SpecCheck ready: ${uiUrl}/\nBackend: ${backendUrl}\nCtrl+C stops only servers started by this launcher.`);
  if (process.env.SPECCHECK_NO_BROWSER !== '1' && process.platform === 'win32') {
    const browser = spawn('powershell.exe', ['-NoProfile', '-WindowStyle', 'Hidden', '-Command', `Start-Process '${uiUrl}/'`], { windowsHide: true, stdio: 'ignore' });
    browser.on('error', (error) => console.error(`Open ${uiUrl}/ manually: ${error.message}`));
  }
} catch (error) {
  console.error(`[ERROR] ${error.message}`);
  await stop(1);
}
