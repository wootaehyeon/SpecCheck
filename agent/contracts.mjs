const severityRank = { info: 0, low: 1, medium: 2, high: 3, critical: 4 };

export function riskLevel(score) {
  if (score >= 85) return 'critical';
  if (score >= 70) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

export function highestSeverity(findings) {
  return findings.reduce(
    (highest, finding) => severityRank[finding.severity] > severityRank[highest] ? finding.severity : highest,
    'info',
  );
}

export function assertDiagnosis(value) {
  const failures = [];
  if (!value || typeof value !== 'object') failures.push('diagnosis must be an object');
  if (value?.schemaVersion !== '1.0.0') failures.push('schemaVersion must be 1.0.0');
  if (!value?.scanId) failures.push('scanId is required');
  if (value?.scanType !== 'basic') failures.push('scanType must be basic');
  if (!['complete', 'partial', 'failed'].includes(value?.status)) failures.push('status is invalid');
  if (!Number.isInteger(value?.risk?.score) || value.risk.score < 0 || value.risk.score > 100) failures.push('risk.score must be an integer from 0 to 100');
  if (!Array.isArray(value?.findings)) failures.push('findings must be an array');
  if (!Array.isArray(value?.resources)) failures.push('resources must be an array');
  if (!Array.isArray(value?.inventory)) failures.push('inventory must be an array');
  if (!Array.isArray(value?.sources)) failures.push('sources must be an array');
  if (!value?.ai?.overview || !Array.isArray(value?.ai?.actionPlan)) failures.push('ai explanation is incomplete');
  if (failures.length) throw new TypeError(`Invalid diagnosis: ${failures.join(', ')}`);
  return value;
}
