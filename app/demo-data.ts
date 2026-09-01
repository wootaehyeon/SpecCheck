import type { Diagnosis } from './types';

export const demoDiagnosis: Diagnosis = {
  schemaVersion: '1.0.0',
  scanId: 'demo-basic-scan',
  scanType: 'basic',
  status: 'complete',
  generatedAt: '2026-09-01T00:42:00.000Z',
  machine: { name: 'DESKTOP-SPECCHECK', os: 'Windows 11 Pro 24H2', agentVersion: '0.3.0' },
  risk: { score: 64, level: 'medium', summary: '즉각적인 장애 징후는 없지만 일부 상태를 추적해야 합니다.' },
  categories: {
    hardware: { count: 1, highestSeverity: 'medium', summary: '하드웨어 점검 항목이 있습니다' },
    software: { count: 0, highestSeverity: 'info', summary: '감지된 소프트웨어 이상 없음' },
    security: { count: 0, highestSeverity: 'info', summary: 'Basic Scan에서 보안 이상 없음' },
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
    actions: ['중요 파일을 별도 저장 장치에 백업', '7일 후 Basic Scan 재실행', 'SSD 펌웨어 업데이트 여부 확인'],
  }],
  inventory: [
    { kind: 'CPU', name: 'AMD Ryzen 7 7800X3D', detail: '8 Cores / 16 Threads', status: 'normal' },
    { kind: 'GPU', name: 'NVIDIA GeForce RTX 4070', detail: '12 GB VRAM', status: 'normal' },
    { kind: 'Memory', name: 'DDR5 32 GB', detail: '6000 MT/s · 2 modules', status: 'normal' },
    { kind: 'Storage', name: 'Samsung SSD 980 PRO 1TB', detail: 'NVMe · Health 86%', status: 'warning' },
  ],
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
    actionPlan: ['중요 파일을 별도 저장 장치에 백업', '7일 후 Basic Scan 재실행', 'SSD 펌웨어 업데이트 여부 확인'],
  },
};
