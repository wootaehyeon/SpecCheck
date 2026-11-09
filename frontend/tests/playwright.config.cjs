const { defineConfig } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const temp = path.join(root, '.deployment-tmp');
fs.mkdirSync(temp, { recursive: true });
const run = fs.mkdtempSync(path.join(temp, 'ui-monitor-'));
// Download routing is tested without shipping a real executable in the test fixture.
const agentBinary = path.join(run, 'SpecCheck-Agent.exe');
fs.writeFileSync(agentBinary, 'MZ-synthetic-browser-test-binary');
const python = process.env.SPECCHECK_TEST_PYTHON || 'python';
const port = Number(process.env.SPECCHECK_TEST_PORT || 8031);
module.exports = defineConfig({
  testDir: __dirname,
  testMatch: '**/*.spec.cjs',
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: process.env.MONITOR_TEST_BROWSER || undefined,
    headless: true,
    viewport: { width: 1365, height: 1000 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `"${python}" -X utf8 -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port ${port}`,
    cwd: root,
    url: `http://127.0.0.1:${port}/health`,
    env: {
      SERVE_FRONTEND: 'true', TELEMETRY_API_ENABLED: 'false', MONITORING_ENABLED: 'true',
      MONITORING_DATABASE_URL: `sqlite:///${path.join(run, 'monitor.db').replaceAll('\\', '/')}`,
      DATA_DIR: run,
      MONITORING_AGENT_EXE: agentBinary,
      NAVER_CLIENT_ID: '', NAVER_CLIENT_SECRET: '', OPENAI_API_KEY: '',
      EBAY_CLIENT_ID: '', EBAY_CLIENT_SECRET: '', EBAY_OAUTH_TOKEN: '',
    },
  },
});
