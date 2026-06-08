const OPEN_MARKET_API_URL = 'http://localhost:8000/api/market-prices';
const CRAWL_API_URL = 'http://localhost:8000/api/crawl';
const PAGE_URLS = {
  main: 'index.html',
  input: 'input.html',
  analyzing: 'analyzing.html',
  result: 'result.html',
  detail: 'detail.html',
  recommend: 'recommend.html',
  crawl: 'crawl.html'
};

function navigateTo(page) {
  const target = PAGE_URLS[page] || page;
  window.location.href = target;
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

    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${part_name}</td>
      <td>${formatPrice(lowestPrice)}</td>
      <td>${formatPrice(avgPrice)}</td>
      <td>
        <span class="sentiment-badge" style="background: #e8f5e9; color: #1b5e20; padding: 4px 8px; border-radius: 4px;">
          ${scorePercent}%
        </span>
      </td>
      <td>
        <small style="color: #666;">
          네이버 쇼핑<br>
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
  const raw = localStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
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

  if (status.includes('비쌈') || status.includes('보류') || status.includes('위험')) {
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

  safeSetValue('purpose', estimate.purpose);
  safeSetValue('cpu', estimate.cpu);
  safeSetValue('cpuPrice', estimate.parts[0]?.userPrice);
  safeSetValue('gpu', estimate.gpu);
  safeSetValue('gpuPrice', estimate.parts[1]?.userPrice);
  safeSetValue('ram', estimate.ram);
  safeSetValue('ramPrice', estimate.parts[2]?.userPrice);
  safeSetValue('storage', estimate.storage);
  safeSetValue('storagePrice', estimate.parts[3]?.userPrice);
  safeSetValue('motherboard', estimate.motherboard);
  safeSetValue('motherboardPrice', estimate.parts[4]?.userPrice);
  safeSetValue('power', estimate.power);
  safeSetValue('powerPrice', estimate.parts[5]?.userPrice);
  safeSetValue('totalPrice', estimate.totalPrice);
}

function getMockMarketPrices(parts) {
  const mockPriceMap = {
    cpu: { lowestPrice: 168000, averagePrice: 182000, mall: '오픈마켓 A', purchaseLink: '' },
    gpu: { lowestPrice: 382000, averagePrice: 405000, mall: '오픈마켓 B', purchaseLink: '' },
    ram: { lowestPrice: 98000, averagePrice: 113000, mall: '오픈마켓 C', purchaseLink: '' },
    storage: { lowestPrice: 85000, averagePrice: 97000, mall: '오픈마켓 A', purchaseLink: '' },
    motherboard: { lowestPrice: 149000, averagePrice: 165000, mall: '오픈마켓 D', purchaseLink: '' },
    power: { lowestPrice: 59000, averagePrice: 69000, mall: '오픈마켓 B', purchaseLink: '' }
  };

  return parts.map((part) => ({
    ...part,
    ...(mockPriceMap[part.key] || { lowestPrice: 0, averagePrice: 0, mall: '-', purchaseLink: '' })
  }));
}

const sampleCrawlResults = [
  {
    source: 'DC인사이드',
    keyword: 'i9-13900K',
    title: '최신 고성능 CPU 구입 후기',
    date: '2026-06-07',
    url: 'https://gall.dcinside.com/mgallery/board/view/?id=cpu&no=12345',
    sentiment: 'positive',
    sentiment_score: 0.85
  },
  {
    source: '당근마켓',
    keyword: 'RTX 4070',
    title: '고급 그래픽카드 중고 거래',
    date: '2026-06-06',
    url: 'https://example.com/item/54321',
    sentiment: 'positive',
    sentiment_score: 0.78
  },
  {
    source: '네이버 카페',
    keyword: '라이젠 7 5700X',
    title: 'CPU 선택에 대한 조언',
    date: '2026-06-05',
    url: 'https://cafe.naver.com/article/12345',
    sentiment: 'neutral',
    sentiment_score: 0.52
  },
  {
    source: 'DC인사이드',
    keyword: 'RTX 4090',
    title: '최고급 그래픽카드 성능 평가',
    date: '2026-06-04',
    url: 'https://gall.dcinside.com/mgallery/board/view/?id=vga&no=98765',
    sentiment: 'positive',
    sentiment_score: 0.72
  }
];

async function fetchCrawlResults(estimate) {
  try {
    const response = await fetch(CRAWL_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ parts: estimate.parts.map((part) => ({ key: part.key, category: part.category, name: part.name })) })
    });

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

  results.forEach((item) => {
    const sentimentBadge = item.sentiment ? `<span class="sentiment-badge sentiment-${item.sentiment}" title="평가 점수: ${(item.sentiment_score * 100).toFixed(0)}%">${item.sentiment}</span>` : '';
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${item.source}</td>
      <td><a href="${item.url}" target="_blank" rel="noreferrer">${item.title}</a></td>
      <td>${item.keyword || '-'}</td>
      <td>${item.date}</td>
      <td>${item.collected_at || '-'}</td>
      <td><a href="${item.url}" target="_blank" rel="noreferrer">열기</a></td>
      <td>${sentimentBadge}</td>
    `;
    tbody.appendChild(row);
  });

  safeSetText('crawlCount', results.length);
  safeSetText('crawlLatestDate', results[0]?.date || '-');
  safeSetText('crawlSources', 'DC인사이드');
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
    const response = await fetch('http://localhost:8000/api/market-intelligence', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ parts: estimate.parts.map((part) => ({ key: part.key, category: part.category, name: part.name })) })
    });

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
  const queryText = estimate?.parts?.map((part) => part.name).filter(Boolean).join(' / ') || '견적을 먼저 등록해 주세요.';

  if (!estimate) {
    renderCrawlData(sampleCrawlResults, queryText, null);
    return;
  }

  // 통합 시장 정보 조회 시도
  fetchMarketIntelligence(estimate).then((marketData) => {
    if (marketData && marketData.data) {
      renderPriceInfo(marketData.data);
    }
  }).catch(() => {
    // 실패 시 무시 (가격 정보는 선택사항)
  });

  // 기존 크롤링 데이터 조회
  fetchCrawlResults(estimate).then((data) => {
    renderCrawlData(data.results || sampleCrawlResults, data.keywords?.join(' / ') || queryText, data.sentiment_summary || null);
  }).catch(() => {
    renderCrawlData(sampleCrawlResults, queryText, null);
  });
}

async function fetchOpenMarketPrices(parts) {
  try {
    const response = await fetch(OPEN_MARKET_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ parts })
    });

    if (!response.ok) {
      throw new Error('API 호출 실패');
    }

    const data = await response.json();
    return data.prices || [];
  } catch (error) {
    console.warn('시장 정보 API가 연결되지 않아 임시 가격 데이터를 사용합니다.', error);
    return getMockMarketPrices(parts);
  }
}

function makePriceComparison(part) {
  const diff = part.userPrice - part.lowestPrice;
  const diffRate = part.lowestPrice > 0 ? (diff / part.lowestPrice) * 100 : 0;

  let status = '적정';
  let badgeClass = 'badge-good';

  if (diffRate >= 15) {
    status = '많이 비쌈';
    badgeClass = 'badge-danger';
  } else if (diffRate >= 5) {
    status = '약간 비쌈';
    badgeClass = 'badge-warning';
  } else if (diffRate <= -5) {
    status = '저렴';
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

function mockAnalyze(estimate, marketPrices) {
  const comparedParts = marketPrices.map(makePriceComparison);
  const inputTotal = comparedParts.reduce((sum, part) => sum + part.userPrice, 0);
  const lowestTotal = comparedParts.reduce((sum, part) => sum + part.lowestPrice, 0);
  const averageTotal = comparedParts.reduce((sum, part) => sum + part.averagePrice, 0);
  const totalDiffRate = lowestTotal > 0 ? ((inputTotal - lowestTotal) / lowestTotal) * 100 : 0;

  const expensiveCount = comparedParts.filter((part) => part.diffRate >= 5).length;
  const priceScore = Math.max(35, Math.round(100 - Math.max(0, totalDiffRate)));
  const balanceScore = 82;
  const compatibilityScore = 76;
  const recencyScore = 86;
  const purposeScore = 80;
  const totalScore = Math.round(
    priceScore * 0.2 +
    balanceScore * 0.25 +
    compatibilityScore * 0.25 +
    purposeScore * 0.2 +
    recencyScore * 0.1
  );
  const riskScore = 100 - totalScore;

  let purchaseStatus = '구매 가능';
  let priceStatus = '적정';
  if (totalDiffRate >= 15 || expensiveCount >= 3) {
    purchaseStatus = '구매 보류';
    priceStatus = '비쌈';
  } else if (totalDiffRate >= 5 || expensiveCount >= 1) {
    purchaseStatus = '조건부 구매';
    priceStatus = '약간 비쌈';
  }

  const mostExpensivePart = [...comparedParts].sort((a, b) => b.diffRate - a.diffRate)[0] || {};

  return {
    purchaseStatus,
    riskScore,
    totalPrice: inputTotal,
    purposeFit: estimate.purpose + '용 적합',
    summary: `입력 견적 합계는 ${formatWon(inputTotal)}이고, 오픈마켓 최저가 합계는 ${formatWon(lowestTotal)}입니다. ${mostExpensivePart.category || '부품'}(${mostExpensivePart.name || 'N/A'}) 가격 차이가 가장 크므로 먼저 확인하는 것이 좋습니다.`,
    priceCompare: {
      parts: comparedParts,
      inputTotal,
      lowestTotal,
      averageTotal,
      totalDiffRate,
      status: priceStatus
    },
    detail: {
      price: {
        score: priceScore,
        status: priceStatus,
        message: `입력 가격이 오픈마켓 최저가 합계보다 약 ${Math.max(0, totalDiffRate).toFixed(1)}% 높습니다. 부품별 가격 비교표에서 차이가 큰 부품을 우선 확인하세요.`
      },
      balance: {
        score: balanceScore,
        status: '양호',
        message: `${estimate.cpu}와 ${estimate.gpu} 조합은 ${estimate.purpose} 기준으로 무난한 편입니다.`
      },
      compatibility: {
        score: compatibilityScore,
        status: '주의 필요',
        message: 'CPU-메인보드 소켓, RAM 규격, 파워 용량은 백엔드 호환성 데이터와 연결해서 최종 판단해야 합니다.'
      },
      recency: {
        score: recencyScore,
        status: '좋음',
        message: '현재 입력된 부품은 최신성 평가용 데이터와 연결하면 출시 연도 기준으로 평가할 수 있습니다.'
      }
    },
    recommendations: [
      {
        category: mostExpensivePart.category || '부품',
        currentPart: mostExpensivePart.name || '-',
        recommendedPart: `${mostExpensivePart.name || '추천 부품'} 오픈마켓 최저가 상품`,
        currentPrice: mostExpensivePart.userPrice || 0,
        recommendedPrice: mostExpensivePart.lowestPrice || 0,
        reason: `${mostExpensivePart.category || '부품'}는 입력 가격과 오픈마켓 최저가 차이가 큽니다. 같은 부품이라면 더 저렴한 판매처를 우선 확인하고, 차이가 계속 크면 대체 부품 추천을 적용하는 것이 좋습니다.`,
        currentPerformance: '78점',
        recommendedPerformance: '동일 또는 유사',
        currentValue: '보통',
        recommendedValue: '개선',
        valueImprovement: Math.max(0, Math.round(mostExpensivePart.diffRate || 0)) + '점',
        performanceImprovement: '가격 개선 중심',
        beforeScore: riskScore,
        afterScore: Math.max(0, riskScore - 10)
      }
    ]
  };
}

function renderPriceCompare(priceCompare) {
  if (!priceCompare) return;
  const tbody = safeGet('priceCompareBody');
  if (!tbody) return;

  tbody.innerHTML = '';

  priceCompare.parts.forEach((part) => {
    const diffClass = part.diff > 0 ? 'price-up' : part.diff < 0 ? 'price-down' : 'price-neutral';
    const diffText = `${part.diff > 0 ? '+' : ''}${formatWon(part.diff)} (${part.diffRate.toFixed(1)}%)`;

    const purchaseInfo = part.purchaseLink
      ? `<a href="${part.purchaseLink}" target="_blank" rel="noreferrer">구매 링크</a>`
      : `${part.mall || ''}`;

    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${part.category}</td>
      <td>${part.name}</td>
      <td>${formatWon(part.userPrice)}</td>
      <td>${formatWon(part.lowestPrice)}<br><small>${purchaseInfo}</small></td>
      <td>${formatWon(part.averagePrice)}</td>
      <td class="${diffClass}">${diffText}</td>
      <td><span class="badge ${part.badgeClass}">${part.status}</span></td>
    `;
    tbody.appendChild(row);
  });

  safeSetText('inputTotalPrice', formatWon(priceCompare.inputTotal));
  safeSetText('marketLowestTotal', formatWon(priceCompare.lowestTotal));
  safeSetText('marketAverageTotal', formatWon(priceCompare.averageTotal));

  const statusEl = safeGet('priceDiffStatus');
  if (statusEl) {
    statusEl.textContent = priceCompare.status;
    setBadgeClass(statusEl, priceCompare.status);
  }
}

function renderResult(result) {
  if (!result) return;

  const purchaseStatus = safeGet('purchaseStatus');
  if (purchaseStatus) {
    purchaseStatus.textContent = result.purchaseStatus;
    setBadgeClass(purchaseStatus, result.purchaseStatus);
  }

  safeSetText('riskScore', result.riskScore + '점');
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
    'CPU-GPU 성능 밸런스 분석 중...',
    '호환성 검사 중...',
    '교체 추천 생성 중...'
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

  fetchOpenMarketPrices(estimate.parts).then((marketPrices) => {
    const result = mockAnalyze(estimate, marketPrices);
    saveData('analysisResult', result);
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
  const result = loadData('analysisResult');
  if (!result) {
    navigateTo('input');
    return;
  }
  renderResult(result);
}

function initPage() {
  const currentPage = getCurrentPageName();
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
