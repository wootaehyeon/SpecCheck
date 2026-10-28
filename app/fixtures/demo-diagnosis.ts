import type { Diagnosis } from '../types';

export const demoDiagnosis: Diagnosis = {
  schemaVersion: '1.2.0',
  scanId: 'demo-basic-scan',
  scanType: 'basic',
  status: 'complete',
  generatedAt: '2026-09-01T00:42:00.000Z',
  machine: { name: 'DESKTOP-SPECCHECK', os: 'Windows 11 Pro 24H2', agentVersion: '0.3.0' },
  risk: { score: 64, level: 'medium', summary: '즉각적인 장애 징후는 없지만 일부 상태를 추적해야 합니다.' },
  categories: {
    hardware: { count: 1, highestSeverity: 'medium', summary: '하드웨어 점검 항목이 있습니다' },
    software: { count: 0, highestSeverity: 'info', summary: '감지된 소프트웨어 이상 없음' },
    security: { count: 0, highestSeverity: 'info', summary: '보안 이벤트를 수집했지만 확정된 이상은 없습니다' },
  },
  resources: [
    { key: 'cpu_usage', label: 'CPU', value: 18, unit: '%', status: 'normal', detail: '4.20 GHz' },
    { key: 'memory_usage', label: '메모리', value: 54, unit: '%', status: 'normal', detail: '17.3 / 32 GB' },
    { key: 'disk_health', label: '시스템 디스크', value: 86, unit: '%', status: 'warning', detail: 'Samsung SSD 980 PRO' },
  ],
  findings: [{
    id: 'finding-storage-001', category: 'hardware', code: 'STORAGE_WEAR_TREND', title: 'SSD 수명 감소 추세', severity: 'medium', confidence: 0.86,
    summary: '현재 사용은 가능하지만 예상 잔여 수명이 이전 기록보다 빠르게 감소하고 있습니다.',
    evidence: ['NVMe Percentage Used: 14%', '7일간 Storage 경고 3회', '건강도 추정치: 86%'],
    rootCauseCandidates: ['누적 쓰기량 증가', '고온 상태에서의 장시간 쓰기 작업'],
    actions: ['중요 파일을 별도 저장 장치에 백업', '7일 후 다시 진단', 'SSD 펌웨어 업데이트 여부 확인'],
    recommendedAction: 'fix',
  }],
  inventory: [
    { kind: 'CPU', name: 'AMD Ryzen 7 7800X3D', detail: '8 Cores / 16 Threads', status: 'normal' },
    { kind: 'GPU', name: 'NVIDIA GeForce RTX 4070', detail: '12 GB VRAM', status: 'normal' },
    { kind: 'Memory', name: 'DDR5 32 GB', detail: '6000 MT/s · 2 modules', status: 'normal' },
    { kind: 'Storage', name: 'Samsung SSD 980 PRO 1TB', detail: 'NVMe · Health 86%', status: 'warning' },
  ],
  rootCauseCandidates: [
    {
      id: 'background_load', rank: 1, confidence: 0.65, action: 'fix',
      title: '백그라운드 작업 부하 후보',
      summary: '높은 CPU 사용량과 동일 프로세스의 생성·통신 활동이 같은 시간대에 관측됐습니다.',
      evidence: ['CPU 사용률 95%', '동일 프로세스의 프로세스 생성·네트워크 연결·DNS 조회 활동', '120초 시간 창에서 상관됨'],
      limitation: '시간상 연관성 기반 후보이며, 원인이나 보안 위협을 확정하지 않습니다.',
    },
    {
      id: 'hardware_instability', rank: 2, confidence: 0.75, action: 'fix',
      title: '하드웨어 불안정 후보',
      summary: 'WHEA 하드웨어 오류와 디스크 오류가 같은 시간대에 관측됐습니다.',
      evidence: ['WHEA 오류 2건', '디스크 오류 1건', '120초 시간 창에서 상관됨'],
      limitation: '시간상 연관성 기반 후보이며, 원인이나 보안 위협을 확정하지 않습니다.',
    },
  ],
  anomalyAnalysis: {
    status: 'signal_detected', method: 'z_score', evaluatedMetrics: 5, requiredBaselineSamples: 3,
    signals: [{
      metric: 'performance.cpu.usage_percent', label: 'CPU 사용률', direction: 'above_baseline',
      zScore: 15, value: 95, baselineMean: 20, samples: 3,
    }],
    limitation: '통계적 상태 변화 신호이며, 고장·보안 위협·교체 필요를 확정하지 않습니다.',
  },
  trajectoryAnalysis: {
    status: 'ready', method: 'linear_regression', requiredSamples: 3, minimumSpanDays: 1,
    trends: [{
      metric: 'storage.free_percent', label: '시스템 드라이브 여유 공간', direction: 'worsening',
      samples: 7, slopePerDay: -0.9, threshold: 10,
      thresholdAt: '2026-12-18T00:00:00.000Z',
      thresholdRange: ['2026-12-02T00:00:00.000Z', '2027-01-10T00:00:00.000Z'],
    }],
    limitation: '선형 추세의 탐색용 근사이며, 실제 고장 시점이나 교체 필요를 예측하지 않습니다.',
  },
  sources: [
    { name: 'wmi', status: 'collected', collectedAt: '2026-09-01T00:42:00.000Z' },
    { name: 'cim', status: 'collected', collectedAt: '2026-09-01T00:42:00.000Z' },
    { name: 'whea', status: 'collected', collectedAt: '2026-09-01T00:42:00.000Z' },
    { name: 'storage', status: 'collected', collectedAt: '2026-09-01T00:42:00.000Z' },
    { name: 'performance', status: 'collected', collectedAt: '2026-09-01T00:42:00.000Z' },
    { name: 'sysmon', status: 'not_in_scope', collectedAt: null },
  ],
  ai: {
    provider: 'template', model: 'deterministic-ko-v1', status: 'fallback',
    overview: 'SSD 수명 감소 추세가 가장 우선입니다. 현재 사용은 가능하지만 백업과 추적 검사가 필요합니다.',
    actionPlan: ['중요 파일을 별도 저장 장치에 백업', '7일 후 다시 진단', 'SSD 펌웨어 업데이트 여부 확인'],
  },
  decision: {
    action: 'fix',
    reason: '설정 및 점검으로 개선 가능한 항목이 있어 구매 전에 조치를 권장합니다.',
    drivenBy: ['STORAGE_WEAR_TREND'],
  },
  recommendations: [],
};
