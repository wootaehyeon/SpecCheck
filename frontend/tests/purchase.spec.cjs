const { test, expect } = require('@playwright/test');

async function monitor(page) {
  await page.addInitScript(() => localStorage.setItem('speccheck.monitor.reader.v1', JSON.stringify({ reader_token: 'sc_read_synthetic', name: 'Test PC' })));
  await page.route('**/api/monitor/**', async (route) => {
    const path = new URL(route.request().url()).pathname.split('/').pop();
    let data = [];
    if (path === 'status') data = { enabled: true };
    if (path === 'latest') data = {
      name: 'Test PC', received_at: Date.now() / 1000, metrics: {},
      snapshot: { sections: { hardware: { status: 'ok', data: {
        cpu: [], gpu: [], storage: [{ model: 'ST2000DM008-2UB102' }], memory: { total_gb: 32 }, motherboard: { product: 'Test board' },
      } } } },
      diagnosis: { findings: [
        { rule_id: 'HW-DISK-001', title: '시스템 드라이브가 HDD', severity: 'high', recommended_action: 'purchase', summary: 'HDD 때문에 부팅이 느립니다.', action_detail: 'SSD 교체를 검토하세요.' },
        { rule_id: 'SW-GPU-001', title: '그래픽 드라이버가 오래됨', severity: 'medium', recommended_action: 'fix', summary: '드라이버 업데이트', action_detail: '공식 드라이버를 설치하세요.' },
      ] },
    };
    await route.fulfill({ json: data });
  });
}

test('HDD diagnosis leads to product selection and a working external purchase link', async ({ page, context }, testInfo) => {
  await monitor(page);
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/purchase/products?**', async (route) => {
    expect(route.request().headers().authorization).toBeUndefined();
    expect(route.request().url()).not.toContain('sc_read');
    await route.fulfill({ json: { status: 'ok', products: [
      { title: '테스트 NVMe SSD 1TB', mall: '테스트 판매처', price: 99000, url: 'https://shop.example/ssd' },
      { title: 'unsafe', mall: '', price: 1, url: 'javascript:alert(1)' },
    ] } });
  });
  await context.route('https://shop.example/ssd', (route) => route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<h1>테스트 판매처 상품</h1>' }));
  await page.goto('/monitor.html');
  await expect(page.locator('.monitor-finding a')).toHaveCount(1);
  await expect(page.locator('.monitor-finding').filter({ hasText: '그래픽 드라이버' }).getByRole('link')).toHaveCount(0);
  await page.getByRole('link', { name: 'SSD 구매하기', exact: true }).click();
  await expect(page).toHaveURL(/purchase.html\?rule=HW-DISK-001$/);
  await expect(page.locator('#diagnosisHeading')).toHaveText('시스템 드라이브가 HDD');
  await expect(page.locator('#currentHardware')).toContainText('ST2000DM008-2UB102');
  await expect(page.locator('#productQuery')).toHaveValue('NVMe SSD 1TB');
  await expect(page.locator('#productList')).toContainText('99,000원');
  await expect(page.locator('.purchase-product')).toHaveCount(1);
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('link', { name: '테스트 NVMe SSD 1TB 구매하기 (새 탭)' }).click();
  const popup = await popupPromise;
  await expect(popup.getByRole('heading')).toHaveText('테스트 판매처 상품');
  expect(await popup.evaluate(() => window.opener === null)).toBe(true);
  await popup.close();
  await page.screenshot({ path: testInfo.outputPath('purchase-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('purchase-mobile.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('missing prices still allow shopping and changing the SSD interface updates the links', async ({ page }) => {
  await page.route('**/api/purchase/products?**', (route) => route.fulfill({ json: { status: 'unconfigured', products: [] } }));
  await page.goto('/purchase.html?rule=HW-DISK-001');
  await expect(page.getByRole('status')).toContainText('가격을 불러오지 못했습니다');
  await expect(page.locator('#naverSearch')).toHaveAttribute('href', `https://search.shopping.naver.com/search/all?query=${encodeURIComponent('NVMe SSD 1TB')}`);
  await page.locator('#partType').selectOption('SATA SSD 1TB');
  await expect(page.locator('#productQuery')).toHaveValue('SATA SSD 1TB');
  await expect(page.locator('#danawaSearch')).toHaveAttribute('href', `https://search.danawa.com/dsearch.php?query=${encodeURIComponent('SATA SSD 1TB')}`);
  await page.locator('#productQuery').fill('삼성 SSD & 2TB');
  await expect(page.locator('#naverSearch')).toHaveAttribute('href', `https://search.shopping.naver.com/search/all?query=${encodeURIComponent('삼성 SSD & 2TB')}`);
  await page.getByRole('button', { name: '상품 검색', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('가격을 불러오지 못했습니다');
});

test('direct access, network failures and empty queries have a usable recovery path', async ({ page }) => {
  await page.route('**/api/purchase/products?**', (route) => route.abort());
  await page.goto('/purchase.html');
  await expect(page.locator('#shoppingLinks')).toBeHidden();
  await page.locator('#productQuery').fill('DDR5 메모리 16GB');
  await page.getByRole('button', { name: '상품 검색', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('쇼핑몰에서 검색과 구매를 계속');
  await expect(page.locator('#naverSearch')).toBeVisible();
  await page.locator('#productQuery').fill('   ');
  await page.getByRole('button', { name: '상품 검색', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('상품명이나 규격을 입력');
  await expect(page.locator('#shoppingLinks')).toBeHidden();
});
