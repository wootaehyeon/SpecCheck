const { defineConfig } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const temp = path.join(root, '.deployment-tmp');
fs.mkdirSync(temp, { recursive: true });
const run = fs.mkdtempSync(path.join(temp, 'ui-monitor-'));
const python = process.env.SPECCHECK_TEST_PYTHON || 'python';
module.exports = defineConfig({
  testDir: __dirname,
  testMatch: '**/*.spec.cjs',
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: 'http://127.0.0.1:8031',
    channel: process.env.MONITOR_TEST_BROWSER || undefined,
    headless: true,
    viewport: { width: 1365, height: 1000 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${python}" -X utf8 -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8031`,
    cwd: root,
    url: 'http://127.0.0.1:8031/health',
    env: {
      SERVE_FRONTEND: 'true', TELEMETRY_API_ENABLED: 'false', MONITORING_ENABLED: 'true',
      MONITORING_DATABASE_URL: `sqlite:///${path.join(run, 'monitor.db').replaceAll('\\', '/')}`,
      NAVER_CLIENT_ID: '', NAVER_CLIENT_SECRET: '', OPENAI_API_KEY: '',
    },
  },
});
