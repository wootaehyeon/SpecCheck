const { test, expect } = require('@playwright/test');

const parts = [
  ['cpu', 'Ryzen 5 7500F', 180000], ['gpu', 'RTX 4060', 430000],
  ['ram', '32GB DDR5', 110000], ['storage', '1TB NVMe SSD', 95000],
  ['motherboard', 'B650M', 160000], ['power', '600W', 65000],
];

async function enter(page, board = 'B650M') {
  await page.goto('/input.html');
  for (const [key, name, price] of parts) {
    await page.locator(`#${key}`).fill(key === 'motherboard' ? board : name);
    await page.locator(`#${key}Price`).fill(String(price));
  }
  await page.locator('#resolution').selectOption('QHD');
  await page.locator('#budget').fill('1200000');
  const evaluation = page.waitForResponse(r => r.url().endsWith('/api/evaluate-build'));
  await page.locator('#startAnalysisButton').click();
  const response = await evaluation;
  expect(response.ok()).toBe(true);
  const data = await response.json();
  await expect(page).toHaveURL(/result.html$/, { timeout: 40000 });
  return data;
}

test('real backend evaluates compatible and incompatible builds; detail preserves calculation', async ({ page }, info) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  const good = await enter(page);
  await expect(page.locator('#purchaseStatus')).toHaveText('조건 확인 필요');
  await expect(page.locator('#marketLowestTotal')).toHaveText('조회 미완료');
  await expect(page.locator('#priceCompareBody')).toContainText('조회 불가');
  await page.goto('/detail.html');
  await expect(page.locator('#balanceDetail')).toContainText(`CPU ${good.cpu_matched || '미등록'}`);
  await expect(page.locator('#balanceDetail')).toContainText(good.cpu_matched ? String(good.cpu_score) : '점수 없음');
  await expect(page.locator('#balanceDetail')).toContainText('현재 PC의 실측 성능이 아닙니다');
  await page.screenshot({ path: info.outputPath('backend-detail.png'), fullPage: true });
  const bad = await enter(page, 'B550M');
  expect(bad.compatibility.issues.some(x => x.type === 'error')).toBe(true);
  await expect(page.locator('#purchaseStatus')).toHaveText('호환성 수정 필요');
  await page.goto('/detail.html');
  for (const issue of bad.compatibility.issues) await expect(page.locator('#compatibilityDetail')).toContainText(issue.message);
  expect(errors).toEqual([]);
});

test('API price success survives navigation and planner apply/undo uses only entered prices', async ({ page }) => {
  await page.route('**/api/market-prices', route => route.fulfill({ json: { prices: parts.map(([key, name]) => ({key, name, lowestPrice:123456, source:'test-provider'})) } }));
  await enter(page);
  await expect(page.locator('#marketLowestTotal')).toHaveText('740,736원');
  await page.goto('/detail.html');
  await page.goto('/result.html');
  await expect(page.locator('#marketLowestTotal')).toHaveText('740,736원');
  await page.goto('/recommend.html');
  await expect(page.locator('[data-apply="rx9060xt16"]')).toBeDisabled();
  await page.locator('details summary').click();
  await page.locator('[data-price-id="rx9060xt16"]').fill('450000');
  await expect(page.locator('[data-apply="rx9060xt16"]')).toBeEnabled();
  await page.locator('[data-apply="rx9060xt16"]').click();
  await expect(page.locator('#recommendInputTotal')).toHaveText('1,060,000원');
  await page.goto('/result.html');
  await expect(page.locator('#priceCompareBody tr').filter({hasText:'RX 9060 XT'})).toContainText('조회 불가');
  await page.goto('/recommend.html');
  await page.locator('#undoReplacement').click();
  await expect(page.locator('#recommendInputTotal')).toHaveText('1,040,000원');
});

test('API failure and old stored demo results cannot create market prices or scores', async ({ page }) => {
  await page.route('**/api/market-prices', route => route.fulfill({status:503,json:{detail:'unavailable'}}));
  await page.route('**/api/evaluate-build', route => route.fulfill({status:503,json:{detail:'unavailable'}}));
  await page.goto('/input.html');
  await page.evaluate(parts => {
    localStorage.setItem('estimateInput', JSON.stringify({purpose:'게임',parts:parts.map(([key,name,userPrice])=>({key,name,userPrice}))}));
    localStorage.setItem('analysisResult', JSON.stringify({riskScore:82,priceCompare:{parts:[{lowestPrice:1,source:'demo'}]}}));
  }, parts);
  await page.goto('/result.html');
  await expect(page.locator('#riskScore')).toHaveText('실측 자료 없음');
  await expect(page.locator('#marketLowestTotal')).toHaveText('조회 미완료');
  await page.goto('/analyzing.html');
  await expect(page).toHaveURL(/result.html$/);
  await page.goto('/detail.html');
  await expect(page.locator('#balanceDetail')).toContainText('견적 평가 API 조회 불가');
  await page.route('**/api/market-intelligence', route => route.fulfill({status:503,json:{}}));
  await page.route('**/api/crawl', route => route.fulfill({status:503,json:{}}));
  await page.goto('/crawl.html');
  await expect(page.locator('#priceInfoBody')).toContainText('조회된 시장 정보가 없습니다');
  await expect(page.locator('#crawlTableBody')).not.toContainText('가성비 끝판왕');
});

test('registered benchmark scores come from backend data and survive detail navigation', async ({ page }) => {
  const cpuDB = require('../../backend/data/cpu_benchmark.json');
  const gpuDB = require('../../backend/data/gpu_benchmark.json');
  await page.goto('/input.html');
  for (const [key, name, price] of parts) {
    const models = {cpu:'Ryzen 7 5700X',gpu:'RTX 3060',motherboard:'B550M',ram:'32GB DDR4'};
    await page.locator(`#${key}`).fill(models[key] || name);
    await page.locator(`#${key}Price`).fill(String(price));
  }
  const evaluation = page.waitForResponse(r => r.url().endsWith('/api/evaluate-build'));
  await page.locator('#startAnalysisButton').click();
  const data = await (await evaluation).json();
  expect(data.cpu_score).toBe(cpuDB['AMD Ryzen 7 5700X'].score);
  expect(data.gpu_score).toBe(gpuDB['GeForce RTX 3060'].score);
  await expect(page).toHaveURL(/result.html$/, {timeout:40000});
  await page.goto('/detail.html');
  await expect(page.locator('#balanceDetail')).toContainText(String(data.cpu_score));
  await expect(page.locator('#balanceDetail')).toContainText(`서버 계산 종합 지수 ${data.overall_score}`);
});
