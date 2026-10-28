import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = fileURLToPath(new URL('..', import.meta.url));
const localPython = fileURLToPath(new URL(process.platform === 'win32' ? '../.venv/Scripts/python.exe' : '../.venv/bin/python', import.meta.url));
const python = process.env.SPECCHECK_PYTHON ?? (existsSync(localPython) ? localPython : process.platform === 'win32' ? 'python' : 'python3');
const [workingDirectory, ...args] = process.argv.slice(2);

if (!workingDirectory || args.length === 0) {
  console.error('Usage: node scripts/run-python.mjs <working-directory> <arguments...>');
  process.exit(2);
}

const result = spawnSync(python, args, {
  cwd: resolve(projectRoot, workingDirectory),
  stdio: 'inherit',
});

if (result.error) {
  console.error(`Python 실행 실패: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
