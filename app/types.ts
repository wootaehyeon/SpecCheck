export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical';
export type HealthStatus = 'normal' | 'warning' | 'critical' | 'unknown';
export type RecommendedAction = 'keep' | 'fix' | 'purchase';

export type MarketPrice = {
  key: string;
  category: string;
  name: string;
  userPrice: number;
  lowestPrice: number;
  highestPrice: number;
  averagePrice: number;
  purchaseLink: string | null;
  productTitle: string | null;
  listingCount: number;
  mall: string | null;
  source: string | null;
  error: string | null;
};

export type MarketPricesResponse = { prices: MarketPrice[] };

export type Diagnosis = {
  schemaVersion: '1.1.0';
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
    recommendedAction: RecommendedAction;
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
  decision: { action: RecommendedAction; reason: string; drivenBy: string[] };
  recommendations: Array<{
    id: string;
    findingIds: string[];
    priority: 'normal' | 'high' | 'urgent';
    category: 'storage' | 'memory';
    title: string;
    description: string;
    searchQuery: string;
    searchUrl: string;
  }>;
};

export type AgentHealth = {
  status: 'ok';
  agentVersion: string;
  host: string;
  backendVersion?: string;
  gemma: { available: boolean; model: string; installed: boolean };
};

export type LocalScanStatus = {
  runId: string | null;
  status: 'idle' | 'running' | 'completed' | 'failed';
  phase: 'idle' | 'permission' | 'collecting' | 'saving' | 'uploading' | 'completed' | 'failed';
  progress: number;
  currentCollector: string | null;
  message: string;
  scanId: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  started?: boolean;
};
