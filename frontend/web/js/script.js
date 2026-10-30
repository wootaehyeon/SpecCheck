// 공개 서버는 웹과 API를 같은 HTTPS 주소로 제공한다.
// 기존 dev-frontend.ps1(5599)로 실행할 때만 로컬 Backend(8000)를 사용한다.
const API_BASE_URL = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)
  && window.location.port === '5599'
  ? `${window.location.protocol}//${window.location.hostname}:8000`
  : '';
const OPEN_MARKET_API_URL = `${API_BASE_URL}/api/market-prices`;
const CRAWL_API_URL = `${API_BASE_URL}/api/crawl`;
const OPTIMIZE_API_URL = `${API_BASE_URL}/api/optimize-estimate`;
const MARKET_INTELLIGENCE_API_URL = `${API_BASE_URL}/api/market-intelligence`;
const DEMO_MARKET_PRICES = true;
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

  marketData.forEach((item) => {
    const { part_name, price_info, market_sentiment } = item;
    const lowestPrice = price_info?.lowest_price || 0;
    const avgPrice = price_info?.average_price || 0;
    const sentiment = market_sentiment ? `${market_sentiment.positive}/${market_sentiment.neutral}/${market_sentiment.negative}` : '-';
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

function getMockMarketPrices(parts) {
  return window.SpecCheckEngine.demoPrices(parts, loadData('candidatePrices') || {});
}

// ===== 시연용 하드코딩 데이터 (확실하게 열리는 실제 링크 사용) =====
// 백엔드 API가 응답하지 않아도 시연 영상에서 항상 동일한 화면이 보이도록 채워둔 예시입니다.
const sampleCrawlResults = [
  {
    source: 'DC인사이드',
    keyword: 'Ryzen 5 7500F',
    title: '7500F 게임용으로 가성비 끝판왕이네요 (구매 후기)',
    date: '2026-06-09',
    collected_at: '2026-06-11',
    url: 'https://gall.dcinside.com/board/lists/?id=computer_new1&s_type=search_subject_memo&s_keyword=7500F',
    sentiment: 'positive',
    sentiment_score: 0.88
  },
  {
    source: '당근마켓',
    keyword: 'RTX 4060',
    title: 'RTX 4060 그래픽카드 미개봉 판매합니다 (직거래/택배)',
    date: '2026-06-10',
    collected_at: '2026-06-11',
    url: 'https://www.daangn.com/search/RTX%204060',
    sentiment: 'positive',
    sentiment_score: 0.81
  },
  {
    source: 'eBay',
    keyword: 'RTX 4060',
    title: 'NVIDIA GeForce RTX 4060 8GB GDDR6 - Used (해외 중고 시세)',
    date: '2026-06-08',
    collected_at: '2026-06-11',
    url: 'https://www.ebay.com/sch/i.html?_nkw=RTX+4060&LH_ItemCondition=3000',
    sentiment: 'neutral',
    sentiment_score: 0.6
  },
  {
    source: 'DC인사이드',
    keyword: '32GB DDR5',
    title: 'DDR5 32GB 요즘 가격 많이 떨어졌네요 (지금이 적기)',
    date: '2026-06-07',
    collected_at: '2026-06-11',
    url: 'https://gall.dcinside.com/board/lists/?id=computer_new1&s_type=search_subject_memo&s_keyword=DDR5+32GB',
    sentiment: 'positive',
    sentiment_score: 0.74
  },
  {
    source: '당근마켓',
    keyword: 'B650M',
    title: 'B650M 메인보드 박스 풀구성 직거래 합니다',
    date: '2026-06-06',
    collected_at: '2026-06-11',
    url: 'https://www.daangn.com/search/B650M',
    sentiment: 'neutral',
    sentiment_score: 0.55
  },
  {
    source: 'eBay',
    keyword: 'Ryzen 5 7500F',
    title: 'AMD Ryzen 5 7500F 6-Core CPU - Tested Working',
    date: '2026-06-05',
    collected_at: '2026-06-11',
    url: 'https://www.ebay.com/sch/i.html?_nkw=Ryzen+5+7500F',
    sentiment: 'positive',
    sentiment_score: 0.79
  }
];

// 커뮤니티 평가 요약(긍정/중립/부정) 시연용 값
const sampleSentimentSummary = {
  total: 6,
  positive: 4,
  neutral: 2,
  negative: 0,
  average_score: 0.73
};

// 부품별 가격 정보 테이블 시연용 값 (네이버/eBay/당근 등에서 수집한 것으로 가정)
const samplePriceInfo = [
  { part_name: 'Ryzen 5 7500F', price_info: { lowest_price: 178000, average_price: 189000 }, market_sentiment: { positive: 42, neutral: 9, negative: 3, average_score: 0.86 } },
  { part_name: 'RTX 4060', price_info: { lowest_price: 389000, average_price: 412000 }, market_sentiment: { positive: 51, neutral: 14, negative: 6, average_score: 0.78 } },
  { part_name: '32GB DDR5', price_info: { lowest_price: 102000, average_price: 118000 }, market_sentiment: { positive: 33, neutral: 7, negative: 2, average_score: 0.82 } },
  { part_name: '1TB NVMe SSD', price_info: { lowest_price: 88000, average_price: 99000 }, market_sentiment: { positive: 28, neutral: 6, negative: 1, average_score: 0.84 } },
  { part_name: 'B650M', price_info: { lowest_price: 145000, average_price: 162000 }, market_sentiment: { positive: 19, neutral: 11, negative: 4, average_score: 0.7 } },
  { part_name: '600W', price_info: { lowest_price: 58000, average_price: 69000 }, market_sentiment: { positive: 22, neutral: 5, negative: 2, average_score: 0.81 } }
];

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
    console.warn('시장 반응 API 호출에 실패하여 샘플 데이터를 표시합니다.', error);
    return { keywords: estimate.parts.map((part) => part.name).filter(Boolean), results: sampleCrawlResults };
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
  const queryText = estimate?.parts?.map((part) => part.name).filter(Boolean).join(' / ') || 'Ryzen 5 7500F / RTX 4060 / 32GB DDR5 / 1TB NVMe SSD / B650M / 600W';

  // 견적이 없어도 시연용 예시 데이터로 화면을 채운다.
  if (!estimate) {
    renderPriceInfo(samplePriceInfo);
    renderCrawlData(sampleCrawlResults, queryText, sampleSentimentSummary);
    return;
  }

  // 통합 시장 정보 조회 시도 (실패 시 예시 가격 정보로 폴백)
  fetchMarketIntelligence(estimate).then((marketData) => {
    renderPriceInfo(marketData && marketData.data ? marketData.data : samplePriceInfo);
  }).catch(() => {
    renderPriceInfo(samplePriceInfo);
  });

  // 기존 크롤링 데이터 조회 (실패 시 예시 데이터로 폴백)
  fetchCrawlResults(estimate).then((data) => {
    renderCrawlData(data.results || sampleCrawlResults, data.keywords?.join(' / ') || queryText, data.sentiment_summary || sampleSentimentSummary);
  }).catch(() => {
    renderCrawlData(sampleCrawlResults, queryText, sampleSentimentSummary);
  });
}

function normalizeMarketPrices(parts, prices) {
  const rows = Array.isArray(prices) ? prices : [];
  return parts.map((part) => {
    const raw = rows.find((item) => item && (item.key === part.key || item.name === part.name)) || {};
    const info = raw.price_info || {};
    const lowest = toNumber(raw.lowestPrice ?? raw.lowest_price ?? info.lowest_price);
    const average = toNumber(raw.averagePrice ?? raw.average_price ?? info.average_price);
    const available = !raw.error && raw.source !== 'error' && Number.isFinite(lowest) && lowest > 0 && Number.isFinite(average) && average > 0;
    return {
      ...part,
      lowestPrice: available ? lowest : null,
      averagePrice: available ? average : null,
      available,
      error: available ? null : (raw.error || '시세 정보를 조회하지 못했습니다.'),
      errorCode: raw.errorCode || raw.error_code || null,
      mall: available ? (raw.mall || raw.source || '-') : '조회 불가',
      purchaseLink: available ? (raw.purchaseLink || raw.purchase_link || '') : ''
    };
  });
}

async function fetchOpenMarketPrices(parts) {
  const controller = new AbortController();
  // The backend can perform six sequential provider calls (8 seconds each).
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

function analyzeEstimate(estimate, marketPrices) {
  const state = window.SpecCheckEngine.inspect(estimate);
  const parts = marketPrices.map(makePriceComparison);
  const inputTotal = parts.reduce((s,p) => s + toNumber(p.userPrice), 0);
  const complete = parts.length > 0 && parts.every(p => p.available !== false);
  const lowestTotal = complete ? parts.reduce((s,p) => s + p.lowestPrice,0) : null;
  const totalDiffRate = lowestTotal > 0 ? (inputTotal-lowestTotal)/lowestTotal*100 : null;
  const errors = state.checks.filter(c => c.status === 'error');
  const status = errors.length ? '호환성 수정 필요' : '조건 확인 필요';
  const prices = complete ? `입력 합계 ${formatWon(inputTotal)}, 데모 기준가 합계 ${formatWon(lowestTotal)}. 차액 ${formatWon(inputTotal-lowestTotal)}입니다.` : '미등록 모델의 가격은 추정하지 않았습니다. 가격 비교가 가능한 부품만 표시합니다.';
  const needs = state.needs.length ? state.needs.join(' / ') : '설정한 용량·코어 기준에서 부족이 확인되지 않았습니다.';
  const recognized = [state.cpu,state.gpu].filter(Boolean);
  return {
    purchaseStatus:status,riskScore:null,totalPrice:inputTotal,
    purposeFit:!state.cpu || !state.gpu || !state.ram.gb ? '모델 확인 필요' : state.needs.length ? '요구 조건 검토' : '용량·코어 기준 충족',
    summary:`${prices} ${errors.length ? '호환성 오류부터 해결하세요.' : '구매 확정 전 BIOS, 케이스, 커넥터를 확인하세요.'} 가격만 데모 값이며 실측 성능 점수는 생성하지 않습니다.`,
    priceCompare:{parts,inputTotal,lowestTotal,averageTotal:null,totalDiffRate,status:complete ? '데모 기준 비교' : '일부 가격 미확인'},
    detail:{
      price:{status:complete ? '데모 가격' : '부분 비교',message:prices},
      balance:{status:'작업 기준 비교',message:needs + ' 이 기준은 용량·코어 계획용이며 FPS나 병목률을 나타내지 않습니다.'},
      compatibility:{status:errors.length ? '오류 확인' : '추가 확인',message:state.checks.map(c => `${c.status === 'error' ? '[불일치]' : c.status === 'pass' ? '[규격 일치]' : '[미확인]'} ${c.message}`).join(' / ')},
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
    const purchaseInfo = part.available === false
      ? `자동 시세를 확인할 수 없습니다.<br><a href="${escapeHtml(searchUrl)}" target="_blank" rel="noopener noreferrer">네이버 쇼핑에서 직접 가격 확인</a>`
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
  if (estimate?.parts) result = analyzeEstimate(estimate, getMockMarketPrices(estimate.parts));

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

  (DEMO_MARKET_PRICES ? Promise.resolve(getMockMarketPrices(estimate.parts)) : fetchOpenMarketPrices(estimate.parts))
    .then((marketPrices) => {
      const result = analyzeEstimate(estimate, marketPrices);
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
  let prices = loadData('candidatePrices') || {};
  const inputTotal = estimate.parts.reduce((s,p) => s + toNumber(p.userPrice),0);
  safeSetValue('recommendBudget', estimate.budget || inputTotal);
  safeSetValue('recommendPurpose', estimate.purpose || '게임');
  safeSetValue('recommendResolution', estimate.resolution || 'FHD');
  safeGet('recommendCuda').checked = !!estimate.cuda || estimate.purpose === 'AI 작업';
  const pricesBody = safeGet('candidatePriceBody');
  pricesBody.innerHTML = engine.catalog.filter(x => x.candidate !== false).map(x => `<tr><td>${escapeHtml(x.name)}</td><td><input type="number" min="0" step="1000" data-price-id="${x.id}" aria-label="${escapeHtml(x.name)} 비교 가격" value="${prices[x.id] ?? x.demo}"></td><td><a href="${x.source}" target="_blank" rel="noopener noreferrer">제조사 사양</a></td></tr>`).join('');
  let latest;
  function recalculate() {
    estimate.purpose = safeGet('recommendPurpose').value;
    estimate.resolution = safeGet('recommendResolution').value;
    estimate.cuda = safeGet('recommendCuda').checked;
    estimate.budget = toNumber(safeGet('recommendBudget').value);
    pricesBody.querySelectorAll('[data-price-id]').forEach(el => { prices[el.dataset.priceId] = toNumber(el.value); });
    saveData('candidatePrices',prices); saveData('estimateInput',estimate);
    latest = engine.recommend(estimate,{budget:estimate.budget,prices});
    safeSetText('recommendInputTotal',formatWon(latest.total));
    safeSetText('recommendRemaining',formatWon(latest.budget-latest.total));
    safeSetText('recommendExplanation',latest.explanation);
    safeSetText('recommendTargets',`작업 기준: RAM ${latest.state.req.ram}GB, CPU ${latest.state.req.cores}코어${latest.state.req.vram ? ', VRAM '+latest.state.req.vram+'GB' : ''}${latest.state.req.cuda ? ', CUDA 필수' : ''}. 계획용 기준이며 프로그램별 실제 요구 사양은 다를 수 있습니다.`);
    safeGet('recommendChecks').innerHTML = latest.state.checks.map(c => `<li class="${c.status === 'error' ? 'price-up' : ''}">${escapeHtml(c.message)} <strong>(${c.status === 'error' ? '불일치' : c.status === 'pass' ? '규격 일치' : '미확인'})</strong></li>`).join('');
    safeGet('recommendCandidates').innerHTML = latest.candidates.length ? latest.candidates.map(c => `<article class="card"><h3>${escapeHtml(c.name)}</h3><p>${escapeHtml(c.current)} 교체 후보 · ${c.eligible ? '예산·등록 규격 조건 통과' : '현재 적용 불가'}</p><p>${escapeHtml(c.reasons.join(' / '))}</p><p>후보 가격 <strong>${formatWon(c.price)}</strong> · 교체 후 전체 견적 <strong>${formatWon(c.total)}</strong> · 차액 ${c.delta > 0 ? '+' : ''}${formatWon(c.delta)}</p><p>${escapeHtml([...c.blocked,...c.conditional].join(' / '))}</p><div class="button-row"><button class="btn btn-primary" data-apply="${c.id}" ${c.eligible ? '' : 'disabled'}>이 후보로 견적 변경</button><a class="btn btn-secondary" href="https://search.shopping.naver.com/search/all?query=${encodeURIComponent(c.name)}" target="_blank" rel="noopener noreferrer">판매 가격 확인</a><a href="${c.source}" target="_blank" rel="noopener noreferrer">제조사 사양</a></div></article>`).join('') : '<div class="card">현재 조건에서 교체할 근거가 있는 등록 후보가 없습니다. 기존 부품 유지 또는 목표·예산 조정을 검토하세요.</div>';
    saveData('analysisResult',analyzeEstimate(estimate,getMockMarketPrices(estimate.parts)));
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
    notice.textContent = DEMO_MARKET_PRICES
      ? '가격 데모 · 시세는 편집 가능한 예시 값입니다. 추천은 입력 사양·용도·예산 조건으로 계산합니다. 실측 FPS·병목률·위험도 점수는 제공하지 않습니다.'
      : '시범 서비스 · 성능·호환성 점수와 교체 추천은 예시 결과입니다. 가격·시장 정보도 조회 실패 시 예시 데이터가 표시될 수 있습니다.';
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
