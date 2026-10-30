import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';

const source = readFileSync(new URL('../frontend/web/js/script.js', import.meta.url), 'utf8');
const parts = [
  { key: 'cpu', category: 'CPU', name: 'Ryzen 5 7500F', userPrice: 180000 },
  { key: 'gpu', category: 'GPU', name: 'RTX 4060', userPrice: 430000 }
];
function setup(fetch = async () => { throw new Error('offline'); }) {
  const elements = new Map();
  const context = vm.createContext({
    window: { location: { hostname: 'example.com', port: '', protocol: 'https:' }, addEventListener() {}, matchMedia: () => ({ matches: true }) },
    document: { getElementById(id) {
      if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', style: {}, classList: { add() {}, remove() {} }, appendChild(row) { this.innerHTML += row.innerHTML; } });
      return elements.get(id);
    }, createElement: () => ({ innerHTML: '' }) },
    console: { warn() {} }, fetch, AbortController, setTimeout, clearTimeout, URL
  });
  vm.runInContext(source.replace('const DEMO_MARKET_PRICES = true;', 'const DEMO_MARKET_PRICES = false;'), context);
  return { context, elements };
}

test('missing API keys do not become zero-price bargains or purchase approval', () => {
  const { context: c, elements } = setup();
  const prices = c.normalizeMarketPrices(parts, parts.map(p => ({ ...p, lowestPrice: 0, averagePrice: 0, source: 'error', error: 'Naver API keys are missing.' })));
  const result = c.mockAnalyze({ purpose: '게임' }, prices);
  assert.equal(result.purchaseStatus, '판정 불가');
  assert.equal(result.riskScore, null);
  assert.equal(result.priceCompare.lowestTotal, null);
  assert.equal(result.recommendations.length, 0);
  c.renderResult(result);
  assert.equal(elements.get('marketLowestTotal').textContent, '조회 미완료');
  assert.match(elements.get('priceCompareBody').innerHTML, /네이버 쇼핑에서 직접 가격 확인/);
  assert.ok(elements.get('priceCompareBody').innerHTML.includes(`query=${encodeURIComponent(parts[0].name)}`));
  assert.doesNotMatch(elements.get('priceCompareBody').innerHTML, />0원|0\.0%|badge-good/);
});

test('partial responses cannot assign another component price or compare incomplete totals', () => {
  const { context: c } = setup();
  const prices = c.normalizeMarketPrices(parts, [{ key: 'gpu', lowestPrice: 400000, averagePrice: 420000 }]);
  assert.equal(prices[0].lowestPrice, null);
  assert.equal(prices[1].lowestPrice, 400000);
  assert.equal(c.mockAnalyze({ purpose: '게임' }, prices).purchaseStatus, '판정 불가');
});

test('successful prices retain real differences and price evaluation', () => {
  const { context: c } = setup();
  const prices = c.normalizeMarketPrices(parts, parts.map(p => ({ ...p, lowestPrice: p.userPrice, averagePrice: p.userPrice })));
  const result = c.mockAnalyze({ purpose: '게임' }, prices);
  assert.equal(result.priceCompare.lowestTotal, 610000);
  assert.equal(result.priceCompare.status, '적정');
  assert.equal(result.priceCompare.parts[0].diff, 0);
});

test('network, HTTP and invalid/empty responses never fall back to mock prices', async () => {
  for (const fetch of [async () => { throw new Error('offline'); }, async () => ({ ok: false }), async () => ({ ok: true, json: async () => ({ prices: [] }) }), async () => ({ ok: true, json: async () => { throw new Error('bad JSON'); } })]) {
    const { context: c } = setup(fetch);
    const prices = await c.fetchOpenMarketPrices(parts);
    assert.ok(prices.every(p => p.lowestPrice === null && !p.available));
  }
});

test('hosted API calls stay on the public origin', async () => {
  let requested;
  const { context: c } = setup(async url => { requested = url; return { ok: true, json: async () => ({ prices: [] }) }; });
  await c.fetchOpenMarketPrices(parts);
  assert.equal(requested, '/api/market-prices');
});

test('previously cached zero-price approvals are corrected when reopened', () => {
  const { context: c, elements } = setup();
  c.renderResult({ purchaseStatus: '구매 가능', riskScore: 16, priceCompare: { parts: parts.map(p => ({ ...p, lowestPrice: 0, averagePrice: 0, status: '적정' })) } });
  assert.equal(elements.get('purchaseStatus').textContent, '판정 불가');
  assert.equal(elements.get('riskScore').textContent, '판정 불가');
});
