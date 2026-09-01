export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type HealthStatus = 'normal' | 'warning' | 'critical' | 'unknown';

export type Diagnosis = {
  schemaVersion: '1.0.0';
  scanId: string;
  scanType: 'basic';
  status: 'complete' | 'partial' | 'failed';
  generatedAt: string;
  machine: { name: string; os: string; agentVersion: string };
  risk: { score: number; level: 'low' | 'medium' | 'high' | 'critical'; summary: string };
  categories: Record<'hardware' | 'software' | 'security', { count: number; highestSeverity: Severity; summary: string }>;
  resources: Array<{ key: string; label: string; value: number; unit: string; status: HealthStatus; detail: string }>;
  findings: Array<{
    id: string;
    category: 'hardware' | 'software' | 'security';
    code: string;
    title: string;
    severity: Severity;
    confidence: number;
    summary: string;
    evidence: string[];
    rootCauseCandidates: string[];
    actions: string[];
  }>;
  inventory: Array<{ kind: string; name: string; detail: string; status: HealthStatus }>;
  sources: Array<{
    name: 'wmi' | 'cim' | 'whea' | 'storage' | 'performance' | 'sysmon';
    status: 'collected' | 'unavailable' | 'permission_required' | 'not_in_scope';
    collectedAt: string | null;
  }>;
  ai: {
    provider: 'ollama' | 'template';
    model: string;
    status: 'generated' | 'fallback' | 'unavailable';
    overview: string;
    actionPlan: string[];
  };
};

export type AgentHealth = {
  status: 'ok';
  agentVersion: string;
  host: string;
  gemma: { available: boolean; model: string; installed: boolean };
};
