'use strict';
(() => {
  const el = (id) => document.getElementById(id);
  const rule = new URLSearchParams(window.location.search).get('rule') || '';
  const profile = window.SpecCheckPurchase.profile(rule);
  const context = window.SpecCheckPurchase.read(rule);
  let pending = null;

  const notes = {
    storage: 'SSD 구매 전 메인보드의 M.2 NVMe 지원 여부와 빈 슬롯을 확인하세요. M.2를 지원하지 않으면 2.5인치 SATA SSD를 검토하세요. 수집 정보만으로 장착 호환성을 확정할 수 없습니다. 교체 전 데이터 백업과 OS 이전도 준비하세요.',
    memory: '메모리 구매 전 DDR4/DDR5 세대, DIMM/SO-DIMM 규격, 빈 슬롯과 최대 지원 용량을 확인하세요. 서로 다른 세대는 호환되지 않습니다. 현재 수집 정보만으로 맞는 규격을 확정할 수 없어 직접 선택이 필요합니다.',
    other: '진단의 조치 내용을 먼저 확인하고 교체할 부품을 특정한 뒤 검색하세요. 상품 검색 결과는 장착 호환성을 보증하지 않습니다.',
  };
  el('compatibilityNote').textContent = notes[profile.category];
  if (context) {
    el('diagnosisHeading').textContent = context.title;
    el('diagnosisSummary').textContent = context.summary;
    if (context.detail) { el('diagnosisDetail').hidden = false; el('diagnosisDetail').textContent = context.detail; }
    const details = [context.board && `메인보드: ${context.board}`,
      profile.category === 'storage' && context.disks && `현재 저장장치: ${context.disks}`,
      profile.category === 'memory' && context.memory && `현재 메모리: ${context.memory}GB`].filter(Boolean);
    el('currentHardware').hidden = !details.length;
    el('currentHardware').textContent = details.join(' · ');
  }
  el('productQuery').value = profile.query;
  el('partType').value = profile.category === 'storage' ? profile.query : '';

  function shoppingLinks(query) {
    el('shoppingLinks').hidden = !query;
    el('ebaySearch').href = `https://www.ebay.com/sch/i.html?_nkw=${encodeURIComponent(query)}`;
    el('naverSearch').href = `https://search.shopping.naver.com/search/all?query=${encodeURIComponent(query)}`;
    el('danawaSearch').href = `https://search.danawa.com/dsearch.php?query=${encodeURIComponent(query)}`;
    el('shoppingQuery').textContent = query ? `검색어: ${query} · 새 탭에서 열립니다.` : '검색어를 입력하면 쇼핑몰 검색 링크가 표시됩니다.';
  }

  function renderProducts(products) {
    el('productList').replaceChildren();
    for (const product of products) {
      let url;
      try { url = new URL(product.url); } catch { continue; }
      const currencies = ['KRW', 'USD', 'EUR', 'GBP', 'CAD', 'AUD'];
      const currency = product.currency ?? 'KRW';
      const amount = Number(product.amount ?? product.price);
      if (url.protocol !== 'https:' || !currencies.includes(currency) || !Number.isFinite(amount) || amount <= 0) continue;
      const money = value => new Intl.NumberFormat('ko-KR', { style: 'currency', currency }).format(Number(value));
      const card = document.createElement('article'); card.className = 'purchase-product';
      const info = document.createElement('div');
      const title = document.createElement('h3'); title.textContent = product.title;
      const mall = document.createElement('p'); mall.textContent = product.mall || 'eBay';
      const price = document.createElement('strong'); price.textContent = currency === 'KRW' ? `${amount.toLocaleString('ko-KR')}원` : `${currency} ${money(amount)}`;
      const buy = document.createElement('a'); buy.className = 'btn btn-primary';
      buy.href = url.href; buy.target = '_blank'; buy.rel = 'noopener noreferrer'; buy.textContent = '구매하기 ↗';
      buy.setAttribute('aria-label', `${product.title} 구매하기 (새 탭)`);
      info.append(title, mall, price);
      if (product.currency) {
        const terms = document.createElement('p');
        terms.textContent = `한국 배송비 ${product.shipping == null ? '미확인' : money(product.shipping)} · 합계 ${product.total == null ? '미확인' : money(product.total)} · 관세·부가세 제외 · ${product.availability === 'in_stock' ? '재고 있음 (판매처 추정)' : '재고 미확인'}`;
        info.append(terms);
      }
      card.append(info, buy); el('productList').append(card);
    }
    return el('productList').childElementCount;
  }

  async function search() {
    const query = el('productQuery').value.trim();
    if (pending) { pending.abort(); pending = null; }
    el('productList').replaceChildren(); shoppingLinks(query);
    if (!query) { el('productList').setAttribute('aria-busy', 'false'); el('productStatus').textContent = '검색할 상품명이나 규격을 입력하세요.'; return; }
    const controller = new AbortController(); pending = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    el('productList').setAttribute('aria-busy', 'true');
    el('productStatus').textContent = '판매 상품과 가격을 조회하고 있습니다. 아래 쇼핑몰에서도 바로 검색할 수 있습니다.';
    try {
      const response = await fetch(`/api/purchase/products?query=${encodeURIComponent(query)}`, { signal: controller.signal });
      if (!response.ok) throw new Error('search failed');
      const data = await response.json();
      if (pending !== controller) return;
      const count = renderProducts(Array.isArray(data.products) ? data.products : []);
      el('productStatus').textContent = count
        ? `${data.source === 'ebay_browse' ? 'eBay' : '판매처'} 상품 ${count}개 · 표시 통화 기준 상품가 · 배송비·관세·부가세·옵션에 따라 최종 금액이 달라집니다.`
        : data.status === 'empty' ? '검색된 상품이 없습니다. 검색어를 바꾸거나 아래 쇼핑몰에서 찾아보세요.'
          : data.status === 'retired' ? '자동 가격 조회가 종료되었습니다. 아래 네이버쇼핑 또는 다나와에서 판매 가격을 확인하고 구매할 수 있습니다.'
          : data.status === 'unconfigured' ? '상품 가격을 불러오지 못했습니다. eBay 실시간 가격 연결이 아직 준비되지 않았습니다. 아래 쇼핑몰에서 판매 가격을 확인할 수 있습니다.'
          : '상품 가격을 불러오지 못했습니다. 아래 네이버쇼핑 또는 다나와에서 상품을 확인하고 구매할 수 있습니다.';
    } catch {
      if (pending === controller) el('productStatus').textContent = '상품 조회가 지연되거나 연결되지 않았습니다. 아래 쇼핑몰에서 검색과 구매를 계속할 수 있습니다.';
    } finally {
      clearTimeout(timeout);
      if (pending === controller) { pending = null; el('productList').setAttribute('aria-busy', 'false'); }
    }
  }
  el('productSearch').addEventListener('submit', (event) => { event.preventDefault(); void search(); });
  el('partType').addEventListener('change', () => {
    if (el('partType').value) { el('productQuery').value = el('partType').value; void search(); }
  });
  el('productQuery').addEventListener('input', () => {
    if (pending) { pending.abort(); pending = null; }
    el('partType').value = '';
    el('productList').replaceChildren(); el('productList').setAttribute('aria-busy', 'false');
    el('productStatus').textContent = '상품 검색을 눌러 변경한 검색어로 조회하세요.';
    shoppingLinks(el('productQuery').value.trim());
  });
  shoppingLinks(profile.query);
  if (profile.query) void search();
})();
