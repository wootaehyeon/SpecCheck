const categories = { cpu: 'CPU', gpu: '그래픽카드', memory: '메모리', storage: '저장장치', motherboard: '메인보드', psu: '파워', case: '케이스', cooler: '쿨러', other: '기타' };
const money = (value) => `${Number(value).toLocaleString('ko-KR')}원`;
const today = () => new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);

/** Both the React app and Docker's static frontend use the same interface. */
export function mountPurchaseHistory(root, { apiBase = '' } = {}) {
  const lifetime = new AbortController();
  const storageKey = `speccheck.purchase.owner.v1:${new URL(apiBase || location.origin).origin}`;
  let mode = 'public', page = 1, buyer = '', loading = null, requestId = null;
  let disposed = false;
  root.classList.add('purchase-history');
  root.innerHTML = `
    <section class="ph-panel" aria-labelledby="ph-title">
      <p class="ph-eyebrow">PURCHASE HISTORY</p><h1 id="ph-title">다른 구매자의 선택을 살펴보세요</h1>
      <p>공유에 동의한 사용자의 구매 부품과 구매 가격을 비교할 수 있습니다. 모든 기록은 사용자 직접 입력이며 결제·영수증 검증을 거치지 않았습니다. 구매자 수는 브라우저 저장키 기준입니다.</p>
      <div class="ph-tabs" aria-label="구매이력 범위"><button type="button" data-mode="public" aria-pressed="true">여러 사용자 구매이력</button><button type="button" data-mode="mine" aria-pressed="false">내 구매이력</button></div>
      <form class="ph-filters" data-role="filters">
        <label>상품명 검색<input name="query" maxlength="120" placeholder="예: SSD 1TB" /></label>
        <label>부품 종류<select name="category"><option value="">전체 부품</option></select></label>
        <button type="submit">검색</button>
      </form>
      <p data-role="buyer" hidden></p>
      <div class="ph-summary" data-role="summary"></div>
      <p data-role="status" role="status" aria-live="polite"></p>
      <div class="ph-records" data-role="records" aria-label="구매이력 목록" aria-busy="false"></div>
      <div class="ph-pagination"><button type="button" data-role="prev">이전</button><span data-role="page"></span><button type="button" data-role="next">다음</button></div>
    </section>
    <section class="ph-panel" aria-labelledby="ph-record-title">
      <h2 id="ph-record-title">구매 내역 기록하기</h2>
      <p>실제로 구매한 부품을 기록하세요. 판매처 링크를 누른 것만으로 구매이력을 저장하지 않습니다. 금액은 원화(KRW)로 입력합니다.</p>
      <form class="ph-entry" data-role="entry">
        <label>상품명<input name="product_name" required maxlength="120" placeholder="제품의 정확한 모델명" /></label>
        <label>부품 종류<select name="category" required><option value="">선택하세요</option></select></label>
        <label>개당 구매 가격 (원)<input name="unit_price" type="number" min="1" max="1000000000" step="1" required inputmode="numeric" /></label>
        <label>수량<input name="quantity" type="number" min="1" max="100" step="1" value="1" required /></label>
        <label>구매일 (한국 기준)<input name="purchased_on" type="date" required /></label>
        <label>판매처 (선택)<input name="merchant" maxlength="80" placeholder="예: 쇼핑몰 이름" /></label>
        <label class="ph-consent"><input name="shared" type="checkbox" />상품명·가격·수량·구매일·판매처를 익명 구매자 표시와 함께 다른 사용자에게 공개하는 데 동의합니다.</label>
        <p class="ph-help">공유는 기본으로 꺼져 있습니다. 이름·연락처·주문번호 등 개인정보는 입력하지 마세요. 내역 관리키는 이 브라우저에 저장됩니다. 브라우저 데이터를 삭제하면 기존 내역을 관리할 수 없습니다.</p>
        <button type="submit" data-role="save">구매이력 저장</button>
      </form>
      <p data-role="saved" role="status" aria-live="polite"></p>
    </section>`;
  const find = (role) => root.querySelector(`[data-role="${role}"]`);
  const filters = find('filters'), entry = find('entry');
  for (const select of root.querySelectorAll('select[name="category"]')) {
    for (const [value, label] of Object.entries(categories)) select.add(new Option(label, value));
  }
  entry.elements.purchased_on.value = today();
  entry.elements.purchased_on.max = today();
  function token(create = false) {
    const existing = localStorage.getItem(storageKey);
    if (/^sc_purchase_[a-f0-9]{64}$/.test(existing || '')) return existing;
    if (!create) return null;
    const value = 'sc_purchase_' + Array.from(crypto.getRandomValues(new Uint8Array(32)), n => n.toString(16).padStart(2, '0')).join('');
    localStorage.setItem(storageKey, value);
    return value;
  }
  async function api(path, { method = 'GET', body, privateRequest = false, signal } = {}) {
    const headers = {};
    if (body) headers['Content-Type'] = 'application/json';
    if (privateRequest) {
      const key = token(method === 'POST');
      if (!key) throw new Error('이 브라우저에 저장된 구매이력이 없습니다.');
      headers.Authorization = `Bearer ${key}`;
    }
    const options = {
      method, headers,
      cache: 'no-store', signal: signal || AbortSignal.any([lifetime.signal, AbortSignal.timeout(15000)]),
    };
    if (body && method !== 'GET' && method !== 'HEAD') options.body = JSON.stringify(body);
    const response = await fetch(`${apiBase}/api/purchase/history${path}`, options);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : '구매이력 요청에 실패했습니다. 입력값과 서버 상태를 확인하세요.');
    }
    return response.status === 204 ? null : response.json();
  }
  function node(tag, text, className) {
    const result = document.createElement(tag); result.textContent = text;
    if (className) result.className = className;
    return result;
  }
  function button(text, action) {
    const result = node('button', text); result.type = 'button';
    result.addEventListener('click', action, { signal: lifetime.signal }); return result;
  }
  async function change(record, remove = false) {
    if (remove && !window.confirm('이 구매이력을 삭제할까요? 공개 목록에서도 삭제됩니다.')) return;
    find('saved').textContent = '';
    try {
      await api(`/${record.id}`, { method: remove ? 'DELETE' : 'PATCH', privateRequest: true, body: remove ? undefined : { shared: !record.shared } });
      if (disposed) return;
      find('saved').textContent = remove ? '구매이력을 삭제했습니다.' : '공유 설정을 변경했습니다.';
      await read();
    } catch (error) { if (!disposed) find('saved').textContent = `변경하지 못했습니다. ${error.message}`; }
  }
  function render(data) {
    find('summary').replaceChildren(...[
      `구매 내역 ${data.summary.records}건`, `구매자 ${data.summary.buyers}명`,
      `기록된 합계 ${money(data.summary.total_spent)}`,
      data.summary.min_unit_price === null ? '가격 기록 없음' : `개당 ${money(data.summary.min_unit_price)} ~ ${money(data.summary.max_unit_price)}`,
    ].map(text => node('span', text)));
    const list = find('records'); list.replaceChildren();
    for (const record of data.items) {
      const card = node('article', '', 'ph-record');
      const heading = node('div', '', 'ph-record-heading');
      heading.append(node('h3', record.product_name), node('span', categories[record.category] || '기타', 'ph-badge'));
      const buyerButton = button(record.buyer_label, () => { buyer = record.buyer_label; page = 1; void read(); });
      buyerButton.className = 'ph-buyer'; buyerButton.disabled = mode === 'mine';
      card.append(heading, buyerButton, node('p', `${record.purchased_on} · ${record.merchant || '판매처 미입력'}`),
        node('p', `개당 ${money(record.unit_price)} × ${record.quantity}개`), node('strong', `합계 ${money(record.total_price)}`),
        node('p', '사용자 직접 기록 · 결제 미검증', 'ph-help'));
      if (mode === 'mine') {
        const actions = node('div', '', 'ph-actions');
        actions.append(node('span', record.shared ? '공유 중' : '나만 보기'),
          button(record.shared ? '공유 중단' : '다른 구매자에게 공유', () => void change(record)), button('삭제', () => void change(record, true)));
        card.append(actions);
      }
      list.append(card);
    }
    const pages = Math.max(1, Math.ceil(data.summary.records / data.page_size));
    find('page').textContent = `${page} / ${pages}`;
    find('prev').disabled = page <= 1; find('next').disabled = page >= pages;
    find('status').textContent = data.items.length ? `${mode === 'mine' ? '이 브라우저의' : '공유된'} 구매이력입니다.` : '조건에 맞는 구매이력이 없습니다.';
  }
  async function read() {
    loading?.abort();
    const controller = new AbortController(); loading = controller;
    find('records').replaceChildren(); find('summary').replaceChildren();
    find('records').setAttribute('aria-busy', 'true'); find('status').textContent = '구매이력을 불러오고 있습니다.';
    find('prev').disabled = true; find('next').disabled = true; find('page').textContent = '';
    const buyerInfo = find('buyer'); buyerInfo.replaceChildren(); buyerInfo.hidden = !buyer || mode === 'mine';
    if (buyer && mode === 'public') buyerInfo.append(node('span', `${buyer}의 기록 `), button('전체 구매자 보기', () => { buyer = ''; page = 1; void read(); }));
    try {
      if (mode === 'mine' && !token()) {
        render({ items: [], summary: { records: 0, buyers: 0, total_spent: 0, min_unit_price: null }, page_size: 20 });
        return;
      }
      const query = new URLSearchParams({ query: filters.elements.query.value.trim(), page: String(page) });
      if (filters.elements.category.value) query.set('category', filters.elements.category.value);
      if (mode === 'public' && buyer) query.set('buyer', buyer);
      const data = await api(`${mode === 'mine' ? '/me' : ''}?${query}`, {
        privateRequest: mode === 'mine', signal: AbortSignal.any([controller.signal, lifetime.signal, AbortSignal.timeout(15000)]),
      });
      if (loading !== controller || disposed) return;
      if (!data.items.length && page > 1) { page = Math.max(1, Math.ceil(data.summary.records / data.page_size)); void read(); return; }
      render(data);
    } catch (error) {
      if (loading === controller && !disposed) find('status').textContent = `구매이력을 불러오지 못했습니다. ${error.message} 검색을 눌러 다시 시도하세요.`;
    } finally {
      if (loading === controller && !disposed) find('records').setAttribute('aria-busy', 'false');
    }
  }
  for (const tab of root.querySelectorAll('[data-mode]')) tab.addEventListener('click', () => {
    mode = tab.dataset.mode; page = 1; buyer = '';
    for (const item of root.querySelectorAll('[data-mode]')) item.setAttribute('aria-pressed', String(item === tab));
    void read();
  }, { signal: lifetime.signal });
  filters.addEventListener('submit', event => { event.preventDefault(); page = 1; void read(); }, { signal: lifetime.signal });
  find('prev').addEventListener('click', () => { page--; void read(); }, { signal: lifetime.signal });
  find('next').addEventListener('click', () => { page++; void read(); }, { signal: lifetime.signal });
  entry.addEventListener('input', () => { requestId = null; }, { signal: lifetime.signal });
  entry.addEventListener('submit', async event => {
    event.preventDefault();
    if (find('save').disabled) return;
    find('save').disabled = true; find('saved').textContent = '구매이력을 저장하고 있습니다.';
    try {
      requestId ||= crypto.randomUUID();
      const form = entry.elements;
      await api('', { method: 'POST', privateRequest: true, body: {
        request_id: requestId, product_name: form.product_name.value.trim(), category: form.category.value,
        unit_price: Number(form.unit_price.value), quantity: Number(form.quantity.value), purchased_on: form.purchased_on.value,
        merchant: form.merchant.value.trim(), shared: form.shared.checked,
      } });
      if (disposed) return;
      find('saved').textContent = '구매이력을 서버에 저장했습니다.';
      entry.reset(); entry.elements.purchased_on.value = today(); requestId = null;
      mode = 'mine'; buyer = ''; page = 1; filters.reset();
      for (const tab of root.querySelectorAll('[data-mode]')) tab.setAttribute('aria-pressed', String(tab.dataset.mode === mode));
      await read();
    } catch (error) { if (!disposed) find('saved').textContent = `저장 여부를 확인하지 못했습니다. ${error.message} 같은 내용으로 다시 저장하면 중복 기록되지 않습니다.`; }
    finally { if (!disposed) find('save').disabled = false; }
  }, { signal: lifetime.signal });
  void read();
  return () => { disposed = true; loading?.abort(); lifetime.abort(); root.replaceChildren(); };
}
