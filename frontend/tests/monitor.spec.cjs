const { test, expect } = require('@playwright/test');
const fs = require('node:fs/promises');
const path = require('node:path');

test('pair a PC, download Agent settings, display real samples, restore viewer and revoke keys', async ({ page, request, browser }, testInfo) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/monitor.html');
  await expect(page.getByText('연결 준비 완료', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '내 PC 연결하고 설정 저장' }).click();
  await expect(page.getByRole('status')).toContainText('먼저 동의');
  await page.locator('#deviceName').fill('Synthetic test PC');
  await page.locator('#basicConsent').check();
  await page.locator('#securityConsent').check();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '내 PC 연결하고 설정 저장' }).click();
  const download = await downloadPromise;
  const config = JSON.parse(await fs.readFile(await download.path(), 'utf8'));
  expect(config.backend_url).toBe('http://127.0.0.1:8031');
  expect(config.writer_token).toMatch(/^sc_write_/);
  expect(config.security_consent).toBe(true);
  await expect(page.locator('#connectionStatus')).toHaveText('Agent 대기');
  const stamp = new Date().toISOString();
  const payload = {
    schema_version: '1.2.0', snapshot_id: 'synthetic-browser-snapshot', device_id: config.device_id,
    collected_at: stamp, scan_mode: 'actual', agent: { version: '0.1.0', os: 'Windows' },
    sections: {
      hardware: { status: 'ok', data: { cpu: [{ name: 'Synthetic CPU <img src=x onerror=alert(1)>' }], gpu: [], memory: { total_gb: 32 }, storage: [], motherboard: {} } },
      performance: { status: 'ok', data: { cpu: { usage_percent: { avg: 48 } }, memory: { available_mb: { avg: 8192 }, committed_percent: { avg: 60 } }, disk: { queue_length: { avg: 0.2 } }, thermal: { max_c: null }, top_processes: [{ name: '<script>bad()</script>', cpu_percent: 5, memory_mb: 100 }] } },
      security: { status: 'ok', data: { consent: { version: 'sysmon-minimal-v1', granted_at: stamp }, window_start: stamp, window_end: stamp, truncated: false, log_gap: false, log_reset: false, log_oldest_at: stamp, events: [{ event_id: 1, record_id: 123, occurred_at: stamp, process_guid: 'synthetic-guid', image: '<img onerror=bad()>' }] } },
    },
  };
  const upload = await request.post('/api/monitor/snapshots', { headers: { Authorization: `Bearer ${config.writer_token}` }, data: payload });
  expect(upload.status()).toBe(201);
  payload.snapshot_id = 'synthetic-browser-snapshot-2';
  expect((await request.post('/api/monitor/snapshots', { headers: { Authorization: `Bearer ${config.writer_token}` }, data: payload })).status()).toBe(201);
  await page.getByRole('button', { name: '새로고침', exact: true }).click();
  await expect(page.locator('#cpuMetric')).toHaveText('48.0%');
  await expect(page.locator('#memoryMetric')).toHaveText('8.0 GB');
  await expect(page.locator('#temperatureMetric')).toHaveText('확인 못함');
  await expect(page.locator('#connectionStatus')).toHaveText('수신 중');
  await expect(page.locator('#hardwareList')).toContainText('<img src=x onerror=alert(1)>');
  await expect(page.locator('#hardwareList img')).toHaveCount(0);
  await expect(page.locator('#processBody script')).toHaveCount(0);
  await expect(page.locator('#eventBody img')).toHaveCount(0);
  await expect(page.locator('#usageChart polyline')).toHaveCount(2);
  await page.screenshot({ path: testInfo.outputPath('monitor-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('#cpuMetric')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('monitor-mobile.png'), fullPage: true });

  const backupPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '조회키 백업', exact: true }).click();
  const backup = await backupPromise;
  const context = await browser.newContext();
  const viewer = await context.newPage();
  await viewer.goto('http://127.0.0.1:8031/monitor.html');
  await viewer.locator('#restoreReader').setInputFiles(await backup.path());
  await expect(viewer.locator('#cpuMetric')).toHaveText('48.0%');
  viewer.once('dialog', (dialog) => dialog.accept());
  await viewer.getByRole('button', { name: '연결 해제·서버 이력 삭제' }).click();
  await expect(viewer.getByRole('status')).toContainText('삭제했습니다');
  expect((await request.post('/api/monitor/snapshots', { headers: { Authorization: `Bearer ${config.writer_token}` }, data: payload })).status()).toBe(401);
  await context.close();
  expect(errors).toEqual([]);
});

test('estimate inputs cannot inject markup into pages sharing monitor credentials', async ({ page }) => {
  await page.goto('/index.html');
  expect(await page.evaluate(() => safeHttpUrl('javascript:alert(1)'))).toBe('#');
  await page.evaluate(() => {
    const table = document.createElement('tbody'); table.id = 'priceCompareBody'; document.body.append(table);
    renderPriceCompare({ parts: [{ category: '<img src=x onerror=bad()>', name: '<svg onload=bad()>', userPrice: 100, lowestPrice: 90, averagePrice: 95, diff: 10, diffRate: 11.1, purchaseLink: 'javascript:bad()', badgeClass: 'badge-good', status: '<script>bad()</script>' }] });
  });
  await expect(page.locator('#priceCompareBody img, #priceCompareBody svg, #priceCompareBody script')).toHaveCount(0);
  await expect(page.locator('#priceCompareBody a')).toHaveAttribute('href', '#');
});

test('an existing PC can enable and disable Sysmon while keeping its connection', async ({ page, request }) => {
  const paired = await request.post('/api/monitor/pair', { data: { name: 'Sysmon settings test', accepted: true, security_accepted: false } });
  const connection = await paired.json();
  await page.addInitScript((value) => localStorage.setItem('speccheck.monitor.reader.v1', JSON.stringify(value)), connection);
  await page.goto('/monitor.html');
  await expect(page.locator('#securityConsentState')).toContainText('꺼짐');
  page.once('dialog', (dialog) => dialog.accept());
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Sysmon 수집 켜기', exact: true }).click();
  const enabled = JSON.parse(await fs.readFile(await (await downloadPromise).path(), 'utf8'));
  expect(enabled.device_id).toBe(connection.device_id);
  expect(enabled.security_consent).toBe(true);
  await expect(page.locator('#securityConsentState')).toContainText('켜짐');
  page.once('dialog', (dialog) => dialog.accept());
  const disabledDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Sysmon 수집 끄기', exact: true }).click();
  const disabled = JSON.parse(await fs.readFile(await (await disabledDownload).path(), 'utf8'));
  expect(disabled.device_id).toBe(connection.device_id);
  expect(disabled.security_consent).toBe(false);
  await expect(page.locator('#securityConsentState')).toContainText('꺼짐');
  await request.delete('/api/monitor/connection', { headers: { Authorization: `Bearer ${connection.reader_token}` } });
});
