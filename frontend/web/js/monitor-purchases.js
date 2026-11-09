'use strict';
(() => {
  const el = (id) => document.getElementById(id);
  let currentKey = null;
  let pending = null;
  const offerTargets = new Map();
  const node = (tag, value, className) => {
    const item = document.createElement(tag);
    if (value) item.textContent = value;
    if (className) item.className = className;
    return item;
  };
  function link(label, href) {
    const item = node('a', label, 'btn btn-secondary');
    item.href = href; item.target = '_blank'; item.rel = 'noopener noreferrer';
    return item;
  }
  function searches(part) {
    const query = encodeURIComponent(part.searchQuery);
    const row = node('div', '', 'button-row');
    row.append(link('네이버쇼핑에서 구매 찾기 ↗', `https://search.shopping.naver.com/search/all?query=${query}`),
      link('다나와 가격 비교 ↗', `https://search.danawa.com/dsearch.php?query=${query}`),
      link('eBay에서 찾기 ↗', `https://www.ebay.com/sch/i.html?_nkw=${query}`));
    return row;
  }
  function clear() {
    pending?.abort(); pending = null; currentKey = null;
    offerTargets.clear();
    el('purchaseRecommendations').replaceChildren();
    el('purchasePriceStatus').textContent = '';
  }
  async function prices(key) {
    const controller = new AbortController(); pending = controller;
    const timeout = setTimeout(() => controller.abort(), 25000);
    const query = new URLSearchParams();
    for (const id of offerTargets.keys()) query.append('product_id', id);
    el('purchasePriceStatus').textContent = '추천 부품의 판매 상품을 확인 중입니다. 쇼핑몰 검색은 바로 이용할 수 있습니다.';
    try {
      // 부품 ID만 전달한다. PC 조회키와 장치 정보는 가격 API·판매처에 보내지 않는다.
      const response = await fetch(`/api/purchase/quotes?${query}`, { signal: controller.signal });
      if (!response.ok) throw new Error('quotes unavailable');
      const data = await response.json();
      if (currentKey !== key || pending !== controller) return;
      let count = 0;
      for (const offer of data.offers || []) {
        const targets = offerTargets.get(offer.product_id);
        if (!targets) continue;
        let url;
        try { url = new URL(offer.url); } catch { continue; }
        const amount = Number(offer.amount);
        if (url.protocol !== 'https:' || !Number.isFinite(amount) || amount <= 0 ||
            !['KRW', 'USD', 'EUR', 'GBP', 'CAD', 'AUD'].includes(offer.currency)) continue;
        const money = value => new Intl.NumberFormat('ko-KR', { style: 'currency', currency: offer.currency }).format(Number(value));
        for (const target of targets) {
          const row = node('div', '', 'monitor-offer');
          row.append(node('strong', `${offer.title} · ${money(amount)}`));
          row.append(node('p', `한국 배송 ${offer.shipping == null ? '미확인' : money(offer.shipping)} · 합계 ${offer.total == null ? '미확인' : money(offer.total)} · 관세·부가세 제외`, 'monitor-help'));
          row.append(link('판매처에서 구매하기 ↗', url.href));
          target.append(row);
        }
        count++;
      }
      el('purchasePriceStatus').textContent = count
        ? `판매 상품 ${count}개 · 새 상품·한국 배송 기준 · 가격과 재고는 판매처에서 최종 확인하세요.`
        : '실시간 가격·재고 미확인 · 위 쇼핑몰에서 추천 모델의 판매 가격을 확인하고 구매할 수 있습니다.';
    } catch {
      if (currentKey === key && pending === controller) el('purchasePriceStatus').textContent = '판매 가격을 불러오지 못했습니다. 위 쇼핑몰 검색으로 구매를 계속할 수 있습니다.';
    } finally {
      clearTimeout(timeout);
      if (pending === controller) pending = null;
    }
  }
  function render(latest) {
    const diagnosis = latest.diagnosis || {};
    const recommendations = diagnosis.recommendations || [];
    const stamp = new Date(latest.snapshot.collected_at).toLocaleString('ko-KR');
    const stale = Date.now() / 1000 - latest.received_at >= 120;
    const findings = (diagnosis.findings || []).filter(item => item.recommended_action === 'purchase');
    const key = JSON.stringify([latest.device_id, latest.snapshot.snapshot_id, recommendations, findings]);
    el('purchaseSummary').textContent = `${stamp} 진단${stale ? ' · 수신 중단 전 마지막 자료' : ''} · ${diagnosis.unavailable
      ? '진단을 완료하지 못해 구매 추천을 만들 수 없습니다.'
      : findings.length ? '확인된 부족·이상 부품에 맞는 구매 후보입니다.'
        : '현재 수집된 범위에서 부품 구매가 필요한 문제는 발견되지 않았습니다. 설정·프로그램 조치가 있으면 먼저 진행하세요.'}`;
    if (currentKey === key) return;
    clear(); currentKey = key;
    if (diagnosis.unavailable) return;
    const covered = new Set();
    for (const recommendation of recommendations) {
      const candidate = recommendation.candidates?.find(item => item.recommended) || recommendation.candidates?.[0];
      if (!candidate?.parts?.length) continue;
      (recommendation.findingIds || []).forEach(id => covered.add(id));
      const card = node('article', '', 'monitor-product');
      card.append(node('p', recommendation.priority === 'urgent' ? '긴급 교체 검토' : '진단 기반 추천', 'monitor-eyebrow'),
        node('h3', candidate.title), node('p', recommendation.description));
      const specs = node('ul');
      for (const part of candidate.parts) specs.append(node('li', `${part.name} · ${(part.specifications || []).join(' / ')}`));
      card.append(specs);
      const cautions = (candidate.checks || []).filter(check => check.status !== 'passed');
      card.append(node('p', candidate.compatibilityStatus === 'passed' ? '수집된 조건 일치 · 실제 장착 환경은 구매 전 확인하세요.' : '장착 조건 추가 확인 필요', 'monitor-help'));
      if (cautions.length) {
        const list = node('ul');
        cautions.forEach(check => list.append(node('li', check.detail)));
        card.append(list);
      }
      for (const part of candidate.parts) {
        card.append(searches(part));
        const target = node('div', '', 'monitor-offers');
        card.append(target);
        if (!offerTargets.has(part.key)) offerTargets.set(part.key, []);
        offerTargets.get(part.key).push(target);
      }
      el('purchaseRecommendations').append(card);
    }
    for (const finding of findings.filter(item => !covered.has(item.rule_id))) {
      const card = node('article', '', 'monitor-product');
      card.append(node('h3', finding.title), node('p', finding.action_detail || finding.summary),
        node('p', '정확한 교체 모델을 정할 자료가 부족합니다. 부품 규격을 먼저 확인하세요.', 'monitor-help'));
      const detail = node('a', '부품 조건 확인하기', 'btn btn-secondary');
      detail.href = `purchase.html?rule=${encodeURIComponent(finding.rule_id)}`;
      detail.addEventListener('click', () => window.SpecCheckPurchase.remember(finding, latest.snapshot.sections?.hardware?.data || {}));
      card.append(detail); el('purchaseRecommendations').append(card);
    }
    if (offerTargets.size) void prices(key);
  }
  window.SpecCheckMonitorPurchases = { render, clear };
})();
