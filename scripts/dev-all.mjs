import { spawn } from 'node:child_process';

const packageManagerCli = process.env.npm_execpath;
if (!packageManagerCli) throw new Error('Run this command through pnpm or npm.');

const children = [
  spawn(process.execPath, ['agent/server.mjs'], { stdio: 'inherit' }),
  spawn(process.execPath, [packageManagerCli, 'dev'], { stdio: 'inherit' }),
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
