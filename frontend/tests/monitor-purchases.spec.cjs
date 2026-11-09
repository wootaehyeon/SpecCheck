const { test, expect } = require('@playwright/test');

test('monitor automatically shows diagnosed products, shopping links and replaces them after recovery', async ({ page, request }, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const connection = await (await request.post('/api/monitor/pair', { data: { name: 'Purchase flow test', accepted: true } })).json();
  const owner = { Authorization: `Bearer ${connection.reader_token}` };
  const writer = await (await request.post('/api/monitor/agent-config', { headers: owner })).json();
  await page.addInitScript(value => localStorage.setItem('speccheck.monitor.reader.v1', JSON.stringify(value)), connection);
  let quoteCalls = 0;
  await page.route('**/api/purchase/quotes?*', async route => {
    quoteCalls++;
    expect(route.request().headers().authorization).toBeUndefined();
    const id = new URL(route.request().url()).searchParams.get('product_id');
    await route.fulfill({ json: { offers: [
      { product_id: id, title: 'Synthetic listing <img src=x>', url: 'https://www.ebay.com/itm/synthetic-test', amount: '100', currency: 'USD', shipping: null, total: null },
      { product_id: id, title: 'Unsafe URL', url: 'javascript:alert(1)', amount: '1', currency: 'USD' },
    ] } });
  });
  await page.goto('/monitor.html');
  await expect(page.locator('#purchasePanel')).toBeHidden();
  const payload = {
    schema_version: '1.2.0', snapshot_id: 'purchase-memory-pressure', device_id: connection.device_id,
    collected_at: new Date().toISOString(), scan_mode: 'actual', agent: { version: '0.1.0', os: 'Windows' },
    sections: {
      hardware: { status: 'ok', data: { cpu: [], gpu: [], memory: { total_gb: 8, modules: [{ rated_speed_mhz: 3200 }], empty_slot_count: 2 }, storage: [], motherboard: {} } },
      performance: { status: 'ok', data: { memory: { available_mb: { avg: 500 }, committed_percent: { avg: 96 } } } },
    },
  };
  expect((await request.post('/api/monitor/snapshots', { headers: { Authorization: `Bearer ${writer.writer_token}` }, data: payload })).status()).toBe(201);
  // No second scan, navigation or shopping action is required after Agent upload.
  await expect(page.locator('#purchasePanel')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('#purchaseSummary')).toContainText('확인된 부족');
  await expect(page.locator('#purchaseRecommendations')).toContainText('DDR4');
  await expect(page.locator('#purchaseRecommendations')).toContainText('장착 조건 추가 확인');
  const naver = page.locator('#purchaseRecommendations a[href^="https://search.shopping.naver.com/"]').first();
  await expect(naver).toBeVisible();
  expect(new URL(await naver.getAttribute('href')).searchParams.get('query')).not.toContain('sc_read_');
  await expect(page.locator('#purchaseRecommendations')).toContainText('Synthetic listing <img src=x>');
  await expect(page.locator('#purchaseRecommendations img, #purchaseRecommendations a[href^="javascript:"]')).toHaveCount(0);
  expect(quoteCalls).toBe(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('recommendations-mobile.png'), fullPage: true });
  payload.snapshot_id = 'purchase-recovered';
  payload.sections.hardware.data.memory.total_gb = 32;
  payload.sections.performance.data.memory = { available_mb: { avg: 10000 }, committed_percent: { avg: 50 } };
  expect((await request.post('/api/monitor/snapshots', { headers: { Authorization: `Bearer ${writer.writer_token}` }, data: payload })).status()).toBe(201);
  await page.getByRole('button', { name: '새로고침', exact: true }).click();
  await expect(page.locator('#purchaseRecommendations')).toBeEmpty();
  await expect(page.locator('#purchaseSummary')).toContainText('구매가 필요한 문제는 발견되지 않았습니다');
  expect(quoteCalls).toBe(1);
  expect(errors).toEqual([]);
  await request.delete('/api/monitor/connection', { headers: owner });
});

test('quote outage preserves immediate shopping links', async ({ page, request }) => {
  const connection = await (await request.post('/api/monitor/pair', { data: { name: 'Quote outage test', accepted: true } })).json();
  const owner = { Authorization: `Bearer ${connection.reader_token}` };
  const writer = await (await request.post('/api/monitor/agent-config', { headers: owner })).json();
  await request.post('/api/monitor/snapshots', { headers: { Authorization: `Bearer ${writer.writer_token}` }, data: {
    schema_version: '1.2.0', snapshot_id: 'quote-outage', device_id: connection.device_id,
    collected_at: new Date().toISOString(), scan_mode: 'actual', agent: { version: '0.1.0', os: 'Windows' },
    sections: { hardware: { status: 'ok', data: { cpu: [], gpu: [], memory: { total_gb: 4 }, storage: [], motherboard: {} } } },
  } });
  await page.addInitScript(value => localStorage.setItem('speccheck.monitor.reader.v1', JSON.stringify(value)), connection);
  await page.route('**/api/purchase/quotes?*', route => route.fulfill({ status: 503, json: {} }));
  await page.goto('/monitor.html');
  await expect(page.locator('#purchasePriceStatus')).toContainText('판매 가격을 불러오지 못했습니다');
  await expect(page.locator('#purchaseRecommendations a').first()).toBeVisible();
  await request.delete('/api/monitor/connection', { headers: owner });
});
