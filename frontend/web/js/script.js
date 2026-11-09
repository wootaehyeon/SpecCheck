// 공개 서버는 웹과 API를 같은 HTTPS 주소로 제공한다.
// 기존 dev-frontend.ps1(5599)로 실행할 때만 로컬 Backend(8000)를 사용한다.
const API_BASE_URL = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)
  && window.location.port === '5599'
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : '';
const OPEN_MARKET_API_URL = `${API_BASE_URL}/api/market-prices`;
const CRAWL_API_URL = `${API_BASE_URL}/api/crawl`;
const MARKET_INTELLIGENCE_API_URL = `${API_BASE_URL}/api/market-intelligence`;
const PAGE_URLS = {
  monitor: 'monitor.html',
  main: 'index.html',
  input: 'input.html',
  analyzing: 'analyzing.html',
  result: 'result.html',
  detail: 'detail.html',
  recommend: 'recommend.html',
  crawl: 'crawl.html'
};

function getCurrentPageName() {
  const file = (window.location.pathname.split('/').pop() || 'index.html').toLowerCase();
  const name = file.replace('.html', '') || 'index';
  return name === 'index' ? 'main' : name;
}

function navigateTo(page) {
  const target = PAGE_URLS[page] || page;
  window.location.href = target;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '#';
  } catch { return '#'; }
}

function formatPrice(price) {
  if (!price || price === 0) return '-';
  return price.toLocaleString('ko-KR') + '원';
}

function renderPriceInfo(marketData) {
  const tbody = safeGet('priceInfoBody');
  if (!tbody || !marketData || !Array.isArray(marketData)) return;

  tbody.innerHTML = '';

  if (!marketData.length) tbody.innerHTML = '<tr><td colspan="5">조회된 시장 정보가 없습니다. 견적과 API 연결 상태를 확인하세요.</td></tr>';
  marketData.forEach((item) => {
    const { part_name, price_info, market_sentiment } = item;
    const lowestPrice = price_info?.lowest_price || 0;
    const avgPrice = price_info?.average_price || 0;
    const scorePercent = market_sentiment ? (market_sentiment.average_score * 100).toFixed(0) : '-';

    const naverLink = `https://search.shopping.naver.com/search/all?query=${encodeURIComponent(part_name)}`;
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${escapeHtml(part_name)}</td>
      <td>${formatPrice(lowestPrice)}</td>
      <td>${formatPrice(avgPrice)}</td>
      <td>
        <span class="sentiment-badge sentiment-positive">
          ${scorePercent}%
        </span>
      </td>
      <td>
        <small class="link-list">
          <a href="${naverLink}" target="_blank" rel="noreferrer">네이버 쇼핑</a><br>
          YouTube<br>
          나무위키
        </small>
      </td>
    `;
    tbody.appendChild(row);
  });
}

function saveData(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function loadData(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (error) {
    console.warn(`저장된 데이터(${key})가 손상되어 초기화합니다.`, error);
    localStorage.removeItem(key);
    return null;
  }
}

function safeGet(id) {
  return document.getElementById(id);
}

function safeSetText(id, text) {
  const el = safeGet(id);
  if (el) el.textContent = text;
}

function safeSetValue(id, value) {
  const el = safeGet(id);
  if (el) el.value = value ?? '';
}

function setBadgeClass(element, status) {
  if (!element) return;
  element.classList.remove('badge-good', 'badge-warning', 'badge-danger');

  if (status.includes('불가')) {
    element.classList.add('badge-warning');
  } else if (status.includes('필요') || status.includes('미확인')) {
    element.classList.add('badge-warning');
  } else if (status.includes('비쌈') || status.includes('보류') || status.includes('위험')) {
    element.classList.add(status.includes('많이') || status.includes('보류') ? 'badge-danger' : 'badge-warning');
  } else {
    element.classList.add('badge-good');
  }
}

function toNumber(value) {
  if (value === null || value === undefined) return 0;
  return Number(String(value).replaceAll(',', '').replaceAll('원', '').trim()) || 0;
}

function formatWon(value) {
  const number = toNumber(value);
  return number.toLocaleString('ko-KR') + '원';
}

function updateTotalPrice() {
  const ids = ['cpuPrice', 'gpuPrice', 'ramPrice', 'storagePrice', 'motherboardPrice', 'powerPrice'];
  const total = ids.reduce((sum, id) => sum + toNumber(safeGet(id)?.value), 0);
  safeSetValue('totalPrice', total);
  return total;
}

function getEstimateInput() {
  const parts = [
    { category: 'CPU', key: 'cpu', name: safeGet('cpu')?.value, userPrice: toNumber(safeGet('cpuPrice')?.value) },
    { category: 'GPU', key: 'gpu', name: safeGet('gpu')?.value, userPrice: toNumber(safeGet('gpuPrice')?.value) },
    { category: 'RAM', key: 'ram', name: safeGet('ram')?.value, userPrice: toNumber(safeGet('ramPrice')?.value) },
    { category: '저장장치', key: 'storage', name: safeGet('storage')?.value, userPrice: toNumber(safeGet('storagePrice')?.value) },
    { category: '메인보드', key: 'motherboard', name: safeGet('motherboard')?.value, userPrice: toNumber(safeGet('motherboardPrice')?.value) },
    { category: '파워', key: 'power', name: safeGet('power')?.value, userPrice: toNumber(safeGet('powerPrice')?.value) }
  ];

  return {
    purpose: safeGet('purpose')?.value || '게임',
    resolution: safeGet('resolution')?.value || 'FHD',
    budget: toNumber(safeGet('budget')?.value) || updateTotalPrice(),
    cpu: parts[0].name,
    gpu: parts[1].name,
    ram: parts[2].name,
    storage: parts[3].name,
    motherboard: parts[4].name,
    power: parts[5].name,
    totalPrice: updateTotalPrice(),
    parts
  };
}

function loadEstimateInput() {
  const estimate = loadData('estimateInput');
  if (!estimate) return;

  const parts = Array.isArray(estimate.parts) ? estimate.parts : [];
  safeSetValue('purpose', estimate.purpose);
  safeSetValue('resolution', estimate.resolution || 'FHD');
  safeSetValue('budget', estimate.budget || 0);
  safeSetValue('cpu', estimate.cpu);
  safeSetValue('cpuPrice', parts[0]?.userPrice);
  safeSetValue('gpu', estimate.gpu);
  safeSetValue('gpuPrice', parts[1]?.userPrice);
  safeSetValue('ram', estimate.ram);
  safeSetValue('ramPrice', parts[2]?.userPrice);
  safeSetValue('storage', estimate.storage);
  safeSetValue('storagePrice', parts[3]?.userPrice);
  safeSetValue('motherboard', estimate.motherboard);
  safeSetValue('motherboardPrice', parts[4]?.userPrice);
  safeSetValue('power', estimate.power);
  safeSetValue('powerPrice', parts[5]?.userPrice);
  safeSetValue('totalPrice', estimate.totalPrice);
}

async function fetchCrawlResults(estimate) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 25000); // 실제 크롤링은 부품당 1~2초 소요되어 여유 있게 설정

    const response = await fetch(CRAWL_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ parts: estimate.parts.map((part) => ({ key: part.key, category: part.category, name: part.name })) }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error('시장 반응 API 호출 실패');
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.warn('시장 반응 API 호출 실패: 조회 결과가 없습니다.', error);
    return { keywords: estimate.parts.map((part) => part.name).filter(Boolean), results: [] };
  }
}

function renderCrawlData(results, queryText = '입력 견적을 먼저 등록해 주세요.', sentimentSummary = null) {
  const tbody = safeGet('crawlTableBody');
  if (!tbody) return;

  tbody.innerHTML = '';

  const rows = results || [];

  if (rows.length === 0) {
    const row = document.createElement('tr');
    row.innerHTML = '<td colspan="9">검색 결과가 없습니다. 다른 키워드로 다시 시도해 주세요.</td>';
    tbody.appendChild(row);
  }

  rows.forEach((item) => {
    const score = Number.isFinite(item.sentiment_score) ? (item.sentiment_score * 100).toFixed(0) : '-';
    const sentimentBadge = item.sentiment ? `<span class="sentiment-badge sentiment-${escapeHtml(item.sentiment)}" title="평가 점수: ${score}%">${escapeHtml(item.sentiment)}</span>` : '';
    const safeUrl = escapeHtml(safeHttpUrl(item.url));
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${escapeHtml(item.source)}</td>
      <td><a href="${safeUrl}" target="_blank" rel="noreferrer">${escapeHtml(item.title)}</a></td>
      <td>${escapeHtml(item.keyword || '-')}</td>
      <td>${escapeHtml(item.date)}</td>
      <td>${escapeHtml(item.collected_at || '-')}</td>
      <td>${item.perplexity != null ? escapeHtml(String(item.perplexity)) : '-'}</td>
      <td>${item.quality_score != null ? escapeHtml(String(item.quality_score)) : '-'}</td>
      <td><a href="${safeUrl}" target="_blank" rel="noreferrer">열기</a></td>
      <td>${sentimentBadge}</td>
    `;
    tbody.appendChild(row);
  });

  safeSetText('crawlCount', rows.length);
  safeSetText('crawlLatestDate', rows[0]?.date || '-');
  const sources = [...new Set(rows.map((item) => item.source).filter(Boolean))];
  safeSetText('crawlSources', sources.length ? sources.join(', ') : 'DC인사이드');

  // 사전학습 모델 품질 평가 요약 (perplexity / quality_score)
  const evaluated = rows.filter((item) => item.perplexity != null && item.quality_score != null);
  safeSetText('avgPerplexity', evaluated.length
    ? (evaluated.reduce((sum, item) => sum + item.perplexity, 0) / evaluated.length).toFixed(2)
    : '-');
  safeSetText('avgQuality', evaluated.length
    ? (evaluated.reduce((sum, item) => sum + item.quality_score, 0) / evaluated.length).toFixed(2)
    : '-');

  safeSetText('crawlQuery', queryText);

  // Display sentiment summary
  if (sentimentSummary) {
    const summaryEl = safeGet('sentimentSummary');
    if (summaryEl) {
      const total = sentimentSummary.total || 1;
      const positivePercent = Math.round((sentimentSummary.positive / total) * 100);
      const neutralPercent = Math.round((sentimentSummary.neutral / total) * 100);
      const negativePercent = Math.round((sentimentSummary.negative / total) * 100);

      const sentimentHTML = `
        <div class="sentiment-stats">
          <div class="stat-item">
            <span>긍정 평가</span>
            <strong class="positive">${sentimentSummary.positive}건</strong>
          </div>
          <div class="stat-item">
            <span>중립 평가</span>
            <strong class="neutral">${sentimentSummary.neutral}건</strong>
          </div>
          <div class="stat-item">
            <span>부정 평가</span>
            <strong class="negative">${sentimentSummary.negative}건</strong>
          </div>
          <div class="stat-item">
            <span>평가 점수</span>
            <strong>${(sentimentSummary.average_score * 100).toFixed(0)}%</strong>
          </div>
        </div>
        <div id="sentimentTrend" class="sentiment-trend">
          <div class="trend-bar">
            <div class="trend-segment positive" style="width: ${positivePercent}%"></div>
            <div class="trend-segment neutral" style="width: ${neutralPercent}%"></div>
            <div class="trend-segment negative" style="width: ${negativePercent}%"></div>
          </div>
          <div class="sentiment-legend">
            <div class="legend-item">
              <div class="legend-color positive"></div>
              <span>긍정: ${positivePercent}%</span>
            </div>
            <div class="legend-item">
              <div class="legend-color neutral"></div>
              <span>중립: ${neutralPercent}%</span>
            </div>
            <div class="legend-item">
              <div class="legend-color negative"></div>
              <span>부정: ${negativePercent}%</span>
            </div>
          </div>
        </div>
      `;
      summaryEl.innerHTML = sentimentHTML;
    }
  }
}

async function fetchMarketIntelligence(estimate) {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 25000); // 실제 크롤링은 부품당 1~2초 소요되어 여유 있게 설정

    const response = await fetch(MARKET_INTELLIGENCE_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ parts: estimate.parts.map((part) => ({ key: part.key, category: part.category, name: part.name })) }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error('시장 정보 API 호출 실패');
    }

    return await response.json();
  } catch (error) {
    console.warn('통합 시장 정보 API 호출 실패:', error);
    return null;
  }
}

function initCrawlPage() {
  const estimate = loadData('estimateInput');
  const queryText = estimate?.parts?.map((part) => part.name).filter(Boolean).join(' / ') || '입력 견적을 먼저 등록해 주세요.';

  // 입력이 없으면 실제 데이터 부재를 표시한다.
  if (!estimate) {
    renderPriceInfo([]);
    renderCrawlData([], queryText, null);
    return;
  }

  // 실패 시 가격을 생성하지 않는다.
  fetchMarketIntelligence(estimate).then((marketData) => {
    renderPriceInfo(marketData && marketData.data ? marketData.data : []);
  }).catch(() => {
    renderPriceInfo([]);
  });

  // 실패 시 게시글과 평판 점수를 생성하지 않는다.
  fetchCrawlResults(estimate).then((data) => {
    renderCrawlData(data.results || [], data.keywords?.join(' / ') || queryText, data.sentiment_summary || null);
  }).catch(() => {
    renderCrawlData([], queryText, null);
  });
}

function normalizeMarketPrices(parts, prices) {
  const rows = Array.isArray(prices) ? prices : [];
  return parts.map((part) => {
    const raw = rows.find((item) => item && (item.key === part.key || item.name === part.name)) || {};
    const info = raw.price_info || {};
    const lowest = toNumber(raw.lowestPrice ?? raw.lowest_price ?? info.lowest_price);
    const average = toNumber(raw.averagePrice ?? raw.average_price ?? info.average_price);
    const available = !raw.error && !['error', 'demo'].includes(raw.source) && Number.isFinite(lowest) && lowest > 0;
    return {
      ...part,
      lowestPrice: available ? lowest : null,
      averagePrice: available && average > 0 ? average : null,
      source: raw.source || null,
      queriedAt: raw.queriedAt || null,
      available,
      error: available ? null : (raw.error || '시세 정보를 조회하지 못했습니다.'),
      errorCode: raw.errorCode || raw.error_code || null,
      nativePrices: Array.isArray(raw.nativePrices) ? raw.nativePrices.filter(price => ['KRW', 'USD', 'EUR', 'GBP', 'CAD', 'AUD'].includes(price.currency) && Number(price.lowest) > 0 && Number.isFinite(Number(price.lowest))) : [],
      mall: available ? (raw.mall || raw.source || '-') : '조회 불가',
      purchaseLink: raw.purchaseLink || raw.purchase_link || ''
    };
  });
}

async function fetchOpenMarketPrices(parts) {
  const controller = new AbortController();
  // eBay detail lookups run in bounded parallel batches on the backend.
  const timeoutId = setTimeout(() => controller.abort(), 60000);
  try {
    const response = await fetch(OPEN_MARKET_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parts }),
      signal: controller.signal
    });
    if (!response.ok) throw new Error('시세 조회 서버에 연결하지 못했습니다.');
    const data = await response.json();
    return normalizeMarketPrices(parts, data.prices || data.data || data);
  } catch (error) {
    console.warn('시세 조회 실패:', error);
    return normalizeMarketPrices(parts, []);
  } finally {
    clearTimeout(timeoutId);
  }
}

async function fetchBuildEvaluation(estimate) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  const state = window.SpecCheckEngine.inspect(estimate);
  const storage = state.get('storage').name;
  const capacity = storage.match(/(\d+(?:\.\d+)?)\s*(TB|GB)/i);
  try {
    const response = await fetch(`${API_BASE_URL}/api/evaluate-build`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({cpu:state.get('cpu').name,gpu:state.get('gpu').name,
        motherboard:state.get('motherboard').name,ram:state.get('ram').name,psu_watt:state.watts,
        storage:storage ? [{type:/NVMe/i.test(storage) ? 'NVMe' : 'SATA',capacity_gb:capacity ? Number(capacity[1])*(capacity[2].toUpperCase() === 'TB' ? 1024 : 1) : null}] : [],
        use_case:estimate.purpose === '게임' ? 'gaming' : estimate.purpose === '사무' ? 'office' : 'workstation'})
    });
    if (!response.ok) throw new Error('견적 평가 API 조회 실패');
    const data = await response.json();
    if (!Array.isArray(data.compatibility?.issues) || !Number.isFinite(data.overall_score)) throw new Error('견적 평가 응답 형식 오류');
    return data;
  } catch (error) {
    console.warn('견적 평가 결과 미확인:', error);
    return null;
  } finally { clearTimeout(timer); }
}

function makePriceComparison(part) {
  if (part.available === false || part.error || !(part.lowestPrice > 0)) {
    return { ...part, available: false, diff: null, diffRate: null, status: '판정 불가', badgeClass: 'badge-warning' };
  }
  const diff = part.userPrice - part.lowestPrice;
  const diffRate = part.lowestPrice > 0 ? (diff / part.lowestPrice) * 100 : 0;

  let status = '기준가 수준';
  let badgeClass = 'badge-good';

  if (diffRate >= 15) {
    status = '기준가보다 15% 이상 높음';
    badgeClass = 'badge-danger';
  } else if (diffRate >= 5) {
    status = '기준가보다 5% 이상 높음';
    badgeClass = 'badge-warning';
  } else if (diffRate <= -5) {
    status = '기준가보다 5% 이상 낮음';
    badgeClass = 'badge-good';
  }

  return {
    ...part,
    diff,
    diffRate,
    status,
    badgeClass
  };
}

function analyzeEstimate(estimate, marketPrices, evaluation = null) {
  const state = window.SpecCheckEngine.inspect(estimate);
  const parts = marketPrices.map(makePriceComparison);
  const inputTotal = parts.reduce((s,p) => s + toNumber(p.userPrice), 0);
  const complete = parts.length > 0 && parts.every(p => p.available !== false);
  const lowestTotal = complete ? parts.reduce((s,p) => s + p.lowestPrice,0) : null;
  const totalDiffRate = lowestTotal > 0 ? (inputTotal-lowestTotal)/lowestTotal*100 : null;
  const serverIssues = evaluation?.compatibility?.issues || [];
  const errors = [...state.checks.filter(c => c.status === 'error'), ...serverIssues.filter(c => c.type === 'error')];
  const status = errors.length ? '호환성 수정 필요' : '조건 확인 필요';
  const basis = '조회한 원화 상품가';
  const prices = complete ? `입력 합계 ${formatWon(inputTotal)}, ${basis} 합계 ${formatWon(lowestTotal)}. 차액 ${formatWon(inputTotal-lowestTotal)}입니다.` : '미확인 가격과 외화 판매가는 원화 견적과 자동 비교하지 않습니다. 배송비·관세·부가세는 별도 확인이 필요합니다.';
  const needs = state.needs.length ? state.needs.join(' / ') : '설정한 용량·코어 기준에서 부족이 확인되지 않았습니다.';
  const recognized = [state.cpu,state.gpu].filter(Boolean);
  return {
    purchaseStatus:status,riskScore:null,totalPrice:inputTotal,
    estimateSignature: JSON.stringify(estimate), evaluation, analysisVersion: 3,
    purposeFit:!state.cpu || !state.gpu || !state.ram.gb ? '모델 확인 필요' : state.needs.length ? '요구 조건 검토' : '용량·코어 기준 충족',
    summary:`${prices} ${errors.length ? '호환성 오류부터 해결하세요.' : '구매 확정 전 BIOS, 케이스, 커넥터를 확인하세요.'} 실측 성능 점수는 생성하지 않습니다.`,
    priceCompare:{parts,inputTotal,lowestTotal,averageTotal:null,totalDiffRate,status:complete ? basis : '일부 가격 미확인'},
    detail:{
      price:{status:complete ? basis : '부분 비교',message:prices},
      balance:{status:'작업 기준 비교',message:(evaluation ? `서버 등록 벤치마크: CPU ${evaluation.cpu_matched || '미등록'} (${evaluation.cpu_matched ? evaluation.cpu_score : '점수 없음'}), GPU ${evaluation.gpu_matched || '미등록'} (${evaluation.gpu_matched ? evaluation.gpu_score : '점수 없음'}). ${evaluation.cpu_matched && evaluation.gpu_matched ? `서버 계산 종합 지수 ${evaluation.overall_score} (${evaluation.tier}). ` : ''}현재 PC의 실측 성능이 아닙니다. ` : '견적 평가 API 조회 불가. ') + needs + ' 이 기준은 용량·코어 계획용이며 FPS나 병목률을 나타내지 않습니다.'},
      compatibility:{status:errors.length ? '오류 확인' : '추가 확인',message:state.checks.map(c => `${c.status === 'error' ? '[불일치]' : c.status === 'pass' ? '[규격 일치]' : '[미확인]'} ${c.message}`).join(' / ') + (evaluation ? ' / 서버 검사: ' + serverIssues.map(c => c.message).join(' / ') : ' / 서버 호환성 검사 미조회')},
      recency:{status:'등록 모델 정보',message:recognized.length ? recognized.map(x => `${x.name}: ${x.year}년 출시`).join(' / ') + '. 출시연도만으로 성능이나 구매 가치를 판단하지 않습니다.' : '정확한 모델을 확인할 수 없습니다.'}
    },recommendations:[]
  };
}

function renderPriceCompare(priceCompare) {
  if (!priceCompare) return;
  const tbody = safeGet('priceCompareBody');
  if (!tbody) return;

  tbody.innerHTML = '';

  priceCompare.parts.forEach((part) => {
    const diffClass = part.diff > 0 ? 'price-up' : part.diff < 0 ? 'price-down' : 'price-neutral';
    const diffText = part.diff == null ? '-' : `${part.diff > 0 ? '+' : ''}${formatWon(part.diff)} (${part.diffRate.toFixed(1)}%)`;

    const searchUrl = `https://search.shopping.naver.com/search/all?query=${encodeURIComponent(part.name || '')}`;
    const native = (part.nativePrices || []).filter(price => ['KRW', 'USD', 'EUR', 'GBP', 'CAD', 'AUD'].includes(price.currency) && Number(price.lowest) > 0 && Number.isFinite(Number(price.lowest)))
      .map(price => `${price.currency} ${new Intl.NumberFormat('ko-KR', { style: 'currency', currency: price.currency }).format(Number(price.lowest))}`).join(' / ');
    const purchaseInfo = part.available === false
      ? `${escapeHtml(part.error || '자동 시세를 확인할 수 없습니다.')}<br>${native ? `eBay 상품가 ${escapeHtml(native)} · 배송비·세금 별도<br>` : ''}${part.purchaseLink ? `<a href="${escapeHtml(safeHttpUrl(part.purchaseLink))}" target="_blank" rel="noopener noreferrer">eBay 상품 확인</a><br>` : ''}<a href="${escapeHtml(searchUrl)}" target="_blank" rel="noopener noreferrer">네이버 쇼핑에서 직접 가격 확인</a>`
      : part.purchaseLink
      ? `<a href="${escapeHtml(safeHttpUrl(part.purchaseLink))}" target="_blank" rel="noreferrer">구매 링크</a>`
      : escapeHtml(part.mall || '');

    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${escapeHtml(part.category)}</td>
      <td>${escapeHtml(part.name)}</td>
      <td>${formatWon(part.userPrice)}</td>
      <td>${part.available === false ? '조회 불가' : formatWon(part.lowestPrice)}<br><small>${purchaseInfo}</small></td>
      <td>${part.averagePrice > 0 ? formatWon(part.averagePrice) : '-'}</td>
      <td class="${diffClass}">${diffText}</td>
      <td><span class="badge ${escapeHtml(part.badgeClass)}">${escapeHtml(part.status)}</span></td>
    `;
    tbody.appendChild(row);
  });

  safeSetText('inputTotalPrice', formatWon(priceCompare.inputTotal));
  safeSetText('marketLowestTotal', priceCompare.lowestTotal == null ? '조회 미완료' : formatWon(priceCompare.lowestTotal));
  safeSetText('marketAverageTotal', priceCompare.averageTotal == null ? '조회 미완료' : formatWon(priceCompare.averageTotal));

  const statusEl = safeGet('priceDiffStatus');
  if (statusEl) {
    statusEl.textContent = priceCompare.status;
    setBadgeClass(statusEl, priceCompare.status);
  }
}

function renderResult(result) {
  if (!result) return;

  const estimate = loadData('estimateInput');
  if (estimate?.parts && (result.analysisVersion !== 3 || result.estimateSignature !== JSON.stringify(estimate))) {
    result = analyzeEstimate(estimate, normalizeMarketPrices(estimate.parts, []));
    saveData('analysisResult', result);
  }

  const purchaseStatus = safeGet('purchaseStatus');
  if (purchaseStatus) {
    purchaseStatus.textContent = result.purchaseStatus;
    setBadgeClass(purchaseStatus, result.purchaseStatus);
  }

  safeSetText('riskScore', result.riskScore == null ? '실측 자료 없음' : result.riskScore + '점');
  safeSetText('resultPrice', formatWon(result.totalPrice));
  safeSetText('purposeFit', result.purposeFit);
  safeSetText('summaryText', result.summary);

  renderPriceCompare(result.priceCompare);

  safeSetText('priceDetail', result.detail?.price?.message || '');
  safeSetText('balanceDetail', result.detail?.balance?.message || '');
  safeSetText('compatibilityDetail', result.detail?.compatibility?.message || '');
  safeSetText('recencyDetail', result.detail?.recency?.message || '');

  const priceBar = safeGet('priceScoreBar');
  if (priceBar) priceBar.style.width = (result.detail?.price?.score || 0) + '%';
  const balanceBar = safeGet('balanceScoreBar');
  if (balanceBar) balanceBar.style.width = (result.detail?.balance?.score || 0) + '%';
  const compatibilityBar = safeGet('compatibilityScoreBar');
  if (compatibilityBar) compatibilityBar.style.width = (result.detail?.compatibility?.score || 0) + '%';
  const recencyBar = safeGet('recencyScoreBar');
  if (recencyBar) recencyBar.style.width = (result.detail?.recency?.score || 0) + '%';

  safeSetText('priceStatus', result.detail?.price?.status || '-');
  safeSetText('balanceStatus', result.detail?.balance?.status || '-');
  safeSetText('compatibilityStatus', result.detail?.compatibility?.status || '-');
  safeSetText('recencyStatus', result.detail?.recency?.status || '-');

  const rec = result.recommendations?.[0];
  if (!rec) safeSetText('recommendReason', '시세 정보를 확인할 수 없어 교체 추천을 보류합니다.');
  if (rec) {
    safeSetText('currentPart', rec.currentPart);
    safeSetText('currentPrice', formatWon(rec.currentPrice));
    safeSetText('currentPerformance', rec.currentPerformance);
    safeSetText('currentValue', rec.currentValue);
    safeSetText('recommendedPart', rec.recommendedPart);
    safeSetText('recommendedPrice', formatWon(rec.recommendedPrice));
    safeSetText('recommendedPerformance', rec.recommendedPerformance);
    safeSetText('recommendedValue', rec.recommendedValue);
    safeSetText('recommendReason', rec.reason);
    safeSetText('valueImprovement', rec.valueImprovement);
    safeSetText('performanceImprovement', rec.performanceImprovement);
    safeSetText('beforeAfterScore', `${rec.beforeScore} → ${rec.afterScore}`);
  }
}

function startAnalysisWorkflow(estimate) {
  const progressBar = safeGet('progressBar');
  const currentStep = safeGet('currentStep');
  const stepItems = document.querySelectorAll('.step-item');
  const steps = [
    '견적 정보 확인 중...',
    '오픈마켓 가격 API 조회 중...',
    '부품별 입력 가격과 API 가격 비교 중...',
    '용도별 사양 기준 비교 중...',
    '호환성 검사 중...',
    '호환성 확인 항목 정리 중...'
  ];

  let index = 0;
  if (progressBar) progressBar.style.width = '0%';

  stepItems.forEach((item, i) => {
    item.className = 'step-item';
    if (i === 0) item.classList.add('current');
  });

  const timer = setInterval(() => {
    const safeIndex = Math.min(index, steps.length - 1);
    const percent = Math.round(((safeIndex + 1) / steps.length) * 100);
    if (progressBar) progressBar.style.width = percent + '%';
    if (currentStep) currentStep.textContent = steps[safeIndex];

    stepItems.forEach((item, i) => {
      item.className = 'step-item';
      if (i < safeIndex) item.classList.add('done');
      if (i === safeIndex) item.classList.add('current');
    });

    index += 1;
  }, 450);

  Promise.all([fetchOpenMarketPrices(estimate.parts), fetchBuildEvaluation(estimate)])
    .then(([marketPrices, evaluation]) => {
      const result = analyzeEstimate(estimate, marketPrices, evaluation);
      saveData('analysisResult', result);
    })
    .catch((error) => {
      console.warn('분석 중 오류가 발생하여 판정을 보류합니다.', error);
      const result = analyzeEstimate(estimate, normalizeMarketPrices(estimate.parts, []));
      saveData('analysisResult', result);
    })
    .finally(() => {
      setTimeout(() => {
        clearInterval(timer);
        if (progressBar) progressBar.style.width = '100%';
        navigateTo('result');
      }, 1600);
    });
}

function initInputPage() {
  loadEstimateInput();

  ['cpuPrice', 'gpuPrice', 'ramPrice', 'storagePrice', 'motherboardPrice', 'powerPrice'].forEach((id) => {
    const el = safeGet(id);
    if (el) el.addEventListener('input', updateTotalPrice);
  });

  const startButton = safeGet('startAnalysisButton');
  if (startButton) {
    startButton.addEventListener('click', () => {
      const estimate = getEstimateInput();
      if (estimate.parts.some(p => !String(p.name || '').trim() || !Number.isFinite(p.userPrice) || p.userPrice <= 0)) {
        let message = safeGet('estimateValidation');
        if (!message) { message = document.createElement('p'); message.id = 'estimateValidation'; message.setAttribute('role','alert'); startButton.before(message); }
        message.textContent = '각 부품의 모델명과 0원보다 큰 가격을 입력하세요. 정확하지 않은 모델은 미확인으로 처리합니다.';
        return;
      }
      saveData('estimateInput', estimate);
      navigateTo('analyzing');
    });
  }

  updateTotalPrice();
}

function initAnalyzingPage() {
  const estimate = loadData('estimateInput');
  if (!estimate) {
    navigateTo('input');
    return;
  }
  startAnalysisWorkflow(estimate);
}

function initResultPage() {
  const result = loadData('analysisResult');
  if (!result) {
    navigateTo('input');
    return;
  }
  renderResult(result);
}

function initDetailPage() {
  const result = loadData('analysisResult');
  if (!result) {
    navigateTo('input');
    return;
  }
  renderResult(result);
}

function initRecommendPage() {
  const estimate = loadData('estimateInput');
  if (!estimate?.parts?.length) { navigateTo('input'); return; }
  const engine = window.SpecCheckEngine;
  const prices = loadData('candidatePrices.v3') || {};
  const inputTotal = estimate.parts.reduce((s,p) => s + toNumber(p.userPrice),0);
  safeSetValue('recommendBudget', estimate.budget || inputTotal);
  safeSetValue('recommendPurpose', estimate.purpose || '게임');
  safeSetValue('recommendResolution', estimate.resolution || 'FHD');
  safeGet('recommendCuda').checked = !!estimate.cuda || estimate.purpose === 'AI 작업';
  const pricesBody = safeGet('candidatePriceBody');
  pricesBody.innerHTML = engine.catalog.filter(x => x.candidate !== false).map(x => `<tr><td>${escapeHtml(x.name)}</td><td><input type="number" min="0" step="1000" data-price-id="${x.id}" aria-label="${escapeHtml(x.name)} 비교 가격" value="${prices[x.id] || ""}"></td><td><a href="${x.source}" target="_blank" rel="noopener noreferrer">제조사 사양</a></td></tr>`).join('');
  pricesBody.insertAdjacentHTML('beforeend', '<tr><td>작업 기준 RAM 전체 키트</td><td><input type="number" min="0" step="1000" data-price-id="ram-capacity" aria-label="RAM 전체 키트 비교 가격" value="'+(prices['ram-capacity'] || '')+'"></td><td>선택한 DDR 규격·총 용량 확인</td></tr>');
  let latest;
  function recalculate() {
    estimate.purpose = safeGet('recommendPurpose').value;
    estimate.resolution = safeGet('recommendResolution').value;
    estimate.cuda = safeGet('recommendCuda').checked;
    estimate.budget = toNumber(safeGet('recommendBudget').value);
    pricesBody.querySelectorAll('[data-price-id]').forEach(el => { prices[el.dataset.priceId] = toNumber(el.value); });
    saveData('candidatePrices.v3',prices); saveData('estimateInput',estimate);
    latest = engine.recommend(estimate,{budget:estimate.budget,prices});
    safeSetText('recommendInputTotal',formatWon(latest.total));
    safeSetText('recommendRemaining',formatWon(latest.budget-latest.total));
    safeSetText('recommendExplanation',latest.explanation);
    safeSetText('recommendTargets',`작업 기준: RAM ${latest.state.req.ram}GB, CPU ${latest.state.req.cores}코어${latest.state.req.vram ? ', VRAM '+latest.state.req.vram+'GB' : ''}${latest.state.req.cuda ? ', CUDA 필수' : ''}. 계획용 기준이며 프로그램별 실제 요구 사양은 다를 수 있습니다.`);
    safeGet('recommendChecks').innerHTML = latest.state.checks.map(c => `<li class="${c.status === 'error' ? 'price-up' : ''}">${escapeHtml(c.message)} <strong>(${c.status === 'error' ? '불일치' : c.status === 'pass' ? '규격 일치' : '미확인'})</strong></li>`).join('');
    safeGet('recommendCandidates').innerHTML = latest.candidates.length ? latest.candidates.map(c => `<article class="card"><h3>${escapeHtml(c.name)}</h3><p>${escapeHtml(c.current)} 교체 후보 · ${c.eligible ? '예산·등록 규격 조건 통과' : '현재 적용 불가'}</p><p>${escapeHtml(c.reasons.join(' / '))}</p><p>${c.price > 0 ? `후보 가격 <strong>${formatWon(c.price)}</strong> · 교체 후 전체 견적 <strong>${formatWon(c.total)}</strong> · 차액 ${c.delta > 0 ? '+' : ''}${formatWon(c.delta)}` : '후보 가격 미입력 · 교체 후 총액과 차액 계산 보류'}</p><p>${escapeHtml([...c.blocked,...c.conditional].join(' / '))}</p><div class="button-row"><button class="btn btn-primary" data-apply="${c.id}" ${c.eligible ? '' : 'disabled'}>이 후보로 견적 변경</button><a class="btn btn-secondary" href="https://search.shopping.naver.com/search/all?query=${encodeURIComponent(c.name)}" target="_blank" rel="noopener noreferrer">판매 가격 확인</a><a href="${c.source}" target="_blank" rel="noopener noreferrer">제조사 사양</a></div></article>`).join('') : '<div class="card">현재 조건에서 교체할 근거가 있는 등록 후보가 없습니다. 기존 부품 유지 또는 목표·예산 조정을 검토하세요.</div>';
    const previous = loadData('analysisResult');
    const retained = (previous?.priceCompare?.parts || []).filter(p => estimate.parts.some(current => current.key === p.key && current.name === p.name));
    const evaluation = previous?.estimateSignature === JSON.stringify(estimate) ? previous.evaluation : null;
    saveData('analysisResult',analyzeEstimate(estimate,normalizeMarketPrices(estimate.parts,retained),evaluation));
  }
  safeGet('recommendForm').addEventListener('input',recalculate);
  pricesBody.addEventListener('input',recalculate);
  safeGet('recommendCandidates').addEventListener('click',event => {
    const button = event.target.closest('[data-apply]');
    if (!button) return;
    const candidate = latest.candidates.find(c => c.id === button.dataset.apply && c.eligible);
    if (!candidate) return;
    saveData('estimateBeforeReplacement',estimate);
    estimate.parts = estimate.parts.map(p => p.key === candidate.key ? {...p,name:candidate.name,userPrice:candidate.price} : p);
    estimate[candidate.key] = candidate.name;
    estimate.totalPrice = estimate.parts.reduce((s,p) => s+toNumber(p.userPrice),0);
    recalculate();
    safeSetText('recommendApplied',`${candidate.name}을 견적에 반영했습니다. 총액 ${formatWon(estimate.totalPrice)}. BIOS·크기·커넥터 확인 후 구매하세요.`);
    safeGet('undoReplacement').hidden = false;
  });
  safeGet('undoReplacement').addEventListener('click',() => {
    const previous = loadData('estimateBeforeReplacement');
    if (previous) { saveData('estimateInput',previous); localStorage.removeItem('estimateBeforeReplacement'); window.location.reload(); }
  });
  safeGet('undoReplacement').hidden = !loadData('estimateBeforeReplacement');
  recalculate();
}

function highlightNav(currentPage) {
  document.querySelectorAll('nav button').forEach((btn) => {
    const onclick = btn.getAttribute('onclick') || '';
    if (onclick.includes(`navigateTo('${currentPage}')`)) {
      btn.classList.add('active');
    }
  });
}

function initPage() {
  const main = document.querySelector('main');
  if (main) {
    const notice = document.createElement('p');
    notice.className = 'service-notice';
    notice.textContent = '등록 사양·서버 평가와 입력 가격으로 검토합니다. 실측 FPS·병목률은 제공하지 않습니다. 조회되지 않은 가격은 미확인으로 표시하며 외화는 원화와 자동 비교하지 않습니다. 배송비·세금은 별도 확인하세요.';
    main.prepend(notice);
  }
  const currentPage = getCurrentPageName();
  highlightNav(currentPage);
  if (currentPage === 'input') {
    initInputPage();
  } else if (currentPage === 'analyzing') {
    initAnalyzingPage();
  } else if (currentPage === 'result') {
    initResultPage();
  } else if (currentPage === 'detail') {
    initDetailPage();
  } else if (currentPage === 'recommend') {
    initRecommendPage();
  } else if (currentPage === 'crawl') {
    initCrawlPage();
  }
}

window.addEventListener('DOMContentLoaded', initPage);

/* ==========================================================================
   Scroll reveal — boxes ease in from blurred to sharp as they enter view.
   Auto-applies to structural boxes; a MutationObserver picks up boxes that
   are rendered after async fetches (tables, result cards, crawl rows).
   ========================================================================== */
(function setupScrollReveal() {
  const prefersReducedMotion = window.matchMedia(
    '(prefers-reduced-motion: reduce)'
  ).matches;
  if (prefersReducedMotion || !('IntersectionObserver' in window)) return;

  const REVEAL_SELECTOR = [
    '.hero-card',
    '.card',
    '.summary-card',
    '.feature-item',
    '.part-card',
    '.stat-item',
    '.table-wrap',
    '.crawl-query',
    '.result-comment',
    '.upload-box',
    '.step-item',
    '.section-title',
    '.section-subtitle'
  ].join(',');

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('in-view');
        io.unobserve(entry.target);
      });
    },
    { threshold: 0.12, rootMargin: '0px 0px -8% 0px' }
  );

  function register(el) {
    if (el.dataset.reveal) return;
    el.dataset.reveal = '1';
    el.classList.add('reveal');
    // Stagger siblings of the same group for a gentle cascade.
    const group = Array.from(el.parentElement?.children || []).filter((c) =>
      c.classList.contains('reveal')
    );
    const index = Math.max(0, group.indexOf(el));
    el.style.transitionDelay = Math.min(index, 6) * 55 + 'ms';
    io.observe(el);
  }

  function scan() {
    document.querySelectorAll(REVEAL_SELECTOR).forEach(register);
  }

  scan();

  // Catch boxes injected after async renders.
  let queued = false;
  const mo = new MutationObserver(() => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      scan();
    });
  });
  mo.observe(document.body, { childList: true, subtree: true });
})();
