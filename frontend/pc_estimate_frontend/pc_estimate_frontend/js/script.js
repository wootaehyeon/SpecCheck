const pages = document.querySelectorAll('.page');

// 실제 백엔드가 준비되면 이 주소를 /api/market-prices 같은 API로 바꾸면 됨.
const OPEN_MARKET_API_URL = 'http://localhost:8000/api/market-prices';

function showPage(pageId) {
  pages.forEach((page) => page.classList.remove('active'));
  document.getElementById(pageId).classList.add('active');
  window.scrollTo({ top: 0, behavior: 'smooth' });
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
  const total = [
    'cpuPrice',
    'gpuPrice',
    'ramPrice',
    'storagePrice',
    'motherboardPrice',
    'powerPrice'
  ].reduce((sum, id) => sum + toNumber(document.getElementById(id).value), 0);

  document.getElementById('totalPrice').value = total;
  return total;
}

function getEstimateInput() {
  const parts = [
    {
      category: 'CPU',
      key: 'cpu',
      name: document.getElementById('cpu').value,
      userPrice: toNumber(document.getElementById('cpuPrice').value)
    },
    {
      category: 'GPU',
      key: 'gpu',
      name: document.getElementById('gpu').value,
      userPrice: toNumber(document.getElementById('gpuPrice').value)
    },
    {
      category: 'RAM',
      key: 'ram',
      name: document.getElementById('ram').value,
      userPrice: toNumber(document.getElementById('ramPrice').value)
    },
    {
      category: '저장장치',
      key: 'storage',
      name: document.getElementById('storage').value,
      userPrice: toNumber(document.getElementById('storagePrice').value)
    },
    {
      category: '메인보드',
      key: 'motherboard',
      name: document.getElementById('motherboard').value,
      userPrice: toNumber(document.getElementById('motherboardPrice').value)
    },
    {
      category: '파워',
      key: 'power',
      name: document.getElementById('power').value,
      userPrice: toNumber(document.getElementById('powerPrice').value)
    }
  ];

  return {
    purpose: document.getElementById('purpose').value,
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

// 백엔드가 없을 때 화면 확인용. 실제 구현 시 fetchOpenMarketPrices()에서 백엔드 응답을 사용하면 됨.
function getMockMarketPrices(parts) {
  const mockPriceMap = {
    cpu: { lowestPrice: 168000, averagePrice: 182000, mall: '오픈마켓 A' },
    gpu: { lowestPrice: 382000, averagePrice: 405000, mall: '오픈마켓 B' },
    ram: { lowestPrice: 98000, averagePrice: 113000, mall: '오픈마켓 C' },
    storage: { lowestPrice: 85000, averagePrice: 97000, mall: '오픈마켓 A' },
    motherboard: { lowestPrice: 149000, averagePrice: 165000, mall: '오픈마켓 D' },
    power: { lowestPrice: 59000, averagePrice: 69000, mall: '오픈마켓 B' }
  };

  return parts.map((part) => ({
    ...part,
    ...(mockPriceMap[part.key] || { lowestPrice: 0, averagePrice: 0, mall: '-' })
  }));
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

    // 기대 응답 형태:
    // { prices: [{ key, category, name, userPrice, lowestPrice, averagePrice, mall }] }
    return data.prices;
  } catch (error) {
    console.warn('오픈마켓 API가 연결되지 않아 임시 가격 데이터를 사용합니다.', error);
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

  const mostExpensivePart = [...comparedParts].sort((a, b) => b.diffRate - a.diffRate)[0];

  return {
    purchaseStatus,
    riskScore,
    totalPrice: inputTotal,
    purposeFit: estimate.purpose + '용 적합',
    summary:
      `입력 견적 합계는 ${formatWon(inputTotal)}이고, 오픈마켓 최저가 합계는 ${formatWon(lowestTotal)}입니다. ` +
      `${mostExpensivePart.category}(${mostExpensivePart.name}) 가격 차이가 가장 크므로 먼저 확인하는 것이 좋습니다.`,
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
        category: mostExpensivePart.category,
        currentPart: mostExpensivePart.name,
        recommendedPart: `${mostExpensivePart.name} 오픈마켓 최저가 상품`,
        currentPrice: mostExpensivePart.userPrice,
        recommendedPrice: mostExpensivePart.lowestPrice,
        reason: `${mostExpensivePart.category}는 입력 가격과 오픈마켓 최저가 차이가 큽니다. 같은 부품이라면 더 저렴한 판매처를 우선 확인하고, 차이가 계속 크면 대체 부품 추천을 적용하는 것이 좋습니다.`,
        currentPerformance: '78점',
        recommendedPerformance: '동일 또는 유사',
        currentValue: '보통',
        recommendedValue: '개선',
        valueImprovement: Math.max(0, Math.round(mostExpensivePart.diffRate)) + '점',
        performanceImprovement: '가격 개선 중심',
        beforeScore: riskScore,
        afterScore: Math.max(0, riskScore - 10)
      }
    ]
  };
}

function setBadgeClass(element, status) {
  element.classList.remove('badge-good', 'badge-warning', 'badge-danger');

  if (status.includes('비쌈') || status.includes('보류') || status.includes('위험')) {
    element.classList.add(status.includes('많이') || status.includes('보류') ? 'badge-danger' : 'badge-warning');
  } else {
    element.classList.add('badge-good');
  }
}

function renderPriceCompare(priceCompare) {
  const tbody = document.getElementById('priceCompareBody');
  tbody.innerHTML = '';

  priceCompare.parts.forEach((part) => {
    const diffClass = part.diff > 0 ? 'price-up' : part.diff < 0 ? 'price-down' : 'price-neutral';
    const diffText = `${part.diff > 0 ? '+' : ''}${formatWon(part.diff)} (${part.diffRate.toFixed(1)}%)`;

    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${part.category}</td>
      <td>${part.name}</td>
      <td>${formatWon(part.userPrice)}</td>
      <td>${formatWon(part.lowestPrice)}<br><small>${part.mall || ''}</small></td>
      <td>${formatWon(part.averagePrice)}</td>
      <td class="${diffClass}">${diffText}</td>
      <td><span class="badge ${part.badgeClass}">${part.status}</span></td>
    `;
    tbody.appendChild(row);
  });

  document.getElementById('inputTotalPrice').textContent = formatWon(priceCompare.inputTotal);
  document.getElementById('marketLowestTotal').textContent = formatWon(priceCompare.lowestTotal);
  document.getElementById('marketAverageTotal').textContent = formatWon(priceCompare.averageTotal);

  const statusEl = document.getElementById('priceDiffStatus');
  statusEl.textContent = priceCompare.status;
  setBadgeClass(statusEl, priceCompare.status);
}

function renderResult(result) {
  const purchaseStatus = document.getElementById('purchaseStatus');
  purchaseStatus.textContent = result.purchaseStatus;
  setBadgeClass(purchaseStatus, result.purchaseStatus);

  document.getElementById('riskScore').textContent = result.riskScore + '점';
  document.getElementById('resultPrice').textContent = formatWon(result.totalPrice);
  document.getElementById('purposeFit').textContent = result.purposeFit;
  document.getElementById('summaryText').textContent = result.summary;

  renderPriceCompare(result.priceCompare);

  document.getElementById('priceDetail').textContent = result.detail.price.message;
  document.getElementById('balanceDetail').textContent = result.detail.balance.message;
  document.getElementById('compatibilityDetail').textContent = result.detail.compatibility.message;
  document.getElementById('recencyDetail').textContent = result.detail.recency.message;

  document.getElementById('priceScoreBar').style.width = result.detail.price.score + '%';
  document.getElementById('balanceScoreBar').style.width = result.detail.balance.score + '%';
  document.getElementById('compatibilityScoreBar').style.width = result.detail.compatibility.score + '%';
  document.getElementById('recencyScoreBar').style.width = result.detail.recency.score + '%';

  document.getElementById('priceStatus').textContent = result.detail.price.status;
  document.getElementById('balanceStatus').textContent = result.detail.balance.status;
  document.getElementById('compatibilityStatus').textContent = result.detail.compatibility.status;
  document.getElementById('recencyStatus').textContent = result.detail.recency.status;

  const rec = result.recommendations[0];
  document.getElementById('currentPart').textContent = rec.currentPart;
  document.getElementById('currentPrice').textContent = formatWon(rec.currentPrice);
  document.getElementById('currentPerformance').textContent = rec.currentPerformance;
  document.getElementById('currentValue').textContent = rec.currentValue;
  document.getElementById('recommendedPart').textContent = rec.recommendedPart;
  document.getElementById('recommendedPrice').textContent = formatWon(rec.recommendedPrice);
  document.getElementById('recommendedPerformance').textContent = rec.recommendedPerformance;
  document.getElementById('recommendedValue').textContent = rec.recommendedValue;
  document.getElementById('recommendReason').textContent = rec.reason;
  document.getElementById('valueImprovement').textContent = rec.valueImprovement;
  document.getElementById('performanceImprovement').textContent = rec.performanceImprovement;
  document.getElementById('beforeAfterScore').textContent = rec.beforeScore + ' → ' + rec.afterScore;
}

async function startAnalysis() {
  const estimate = getEstimateInput();
  showPage('analyzing');

  const progressBar = document.getElementById('progressBar');
  const currentStep = document.getElementById('currentStep');
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
  progressBar.style.width = '0%';

  stepItems.forEach((item, i) => {
    item.className = 'step-item';
    if (i === 0) item.classList.add('current');
  });

  const timer = setInterval(() => {
    const safeIndex = Math.min(index, steps.length - 1);
    const percent = Math.round(((safeIndex + 1) / steps.length) * 100);
    progressBar.style.width = percent + '%';
    currentStep.textContent = steps[safeIndex];

    stepItems.forEach((item, i) => {
      item.className = 'step-item';
      if (i < safeIndex) item.classList.add('done');
      if (i === safeIndex) item.classList.add('current');
    });

    index++;
  }, 450);

  const marketPrices = await fetchOpenMarketPrices(estimate.parts);
  const result = mockAnalyze(estimate, marketPrices);

  setTimeout(() => {
    clearInterval(timer);
    progressBar.style.width = '100%';
    renderResult(result);
    showPage('result');
  }, 1600);
}

['cpuPrice', 'gpuPrice', 'ramPrice', 'storagePrice', 'motherboardPrice', 'powerPrice'].forEach((id) => {
  document.getElementById(id).addEventListener('input', updateTotalPrice);
});

updateTotalPrice();
