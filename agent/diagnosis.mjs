import { highestSeverity, riskLevel } from './contracts.mjs';

const categoryCopy = {
  hardware: ['감지된 하드웨어 이상 없음', '하드웨어 점검 항목이 있습니다'],
  software: ['감지된 소프트웨어 이상 없음', '소프트웨어 점검 항목이 있습니다'],
  security: ['Basic Scan에서 보안 이상 없음', '보안 점검 항목이 있습니다'],
};

function categorySummary(category, findings) {
  const selected = findings.filter((finding) => finding.category === category);
  return {
    count: selected.length,
    highestSeverity: highestSeverity(selected),
    summary: categoryCopy[category][selected.length ? 1 : 0],
  };
}

export function buildDiagnosis(snapshot, { scanId, generatedAt, ai }) {
  const score = Math.max(0, Math.min(100, Math.round(snapshot.riskScore ?? 0)));
  const collectedSources = snapshot.sources.filter((source) => source.status === 'collected').length;
  const status = collectedSources >= 4 ? 'complete' : 'partial';
  const riskSummary = score >= 70
    ? '빠른 점검과 조치가 필요한 위험 신호가 확인되었습니다.'
    : score >= 40
      ? '즉각적인 장애 징후는 없지만 일부 상태를 추적해야 합니다.'
      : '현재 수집 범위에서 뚜렷한 이상 징후가 없습니다.';

  return {
    schemaVersion: '1.0.0',
    scanId,
    scanType: 'basic',
    status,
    generatedAt,
    machine: snapshot.machine,
    risk: { score, level: riskLevel(score), summary: riskSummary },
    categories: {
      hardware: categorySummary('hardware', snapshot.findings),
      software: categorySummary('software', snapshot.findings),
      security: categorySummary('security', snapshot.findings),
    },
    resources: snapshot.resources,
    findings: snapshot.findings,
    inventory: snapshot.inventory,
    sources: snapshot.sources.map((source) => ({
      ...source,
      collectedAt: source.status === 'collected' ? generatedAt : null,
    })),
    ai,
  };
}
