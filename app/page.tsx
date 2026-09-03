'use client';

import { useEffect, useState } from 'react';
import {
  Activity,
  Bot,
  Check,
  Cpu,
  Database,
  Gauge,
  HardDrive,
  Info,
  MemoryStick,
  Radar,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  WifiOff,
} from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

import { diagnosticsConfig } from './config';
import { DiagnosticsApiError, getAgentHealth, getLatestDiagnosis, runBasicScan } from './diagnostics-client';
import { demoDiagnosis } from './fixtures/demo-diagnosis';
import type { AgentHealth, Diagnosis } from './types';

type ConnectionState = 'checking' | 'live' | 'empty' | 'offline' | 'demo' | 'error';

const riskTone = {
  low: { badge: 'bg-emerald-300 text-emerald-950', bar: '[&_[data-slot=progress-indicator]]:bg-emerald-300', label: 'LOW' },
  medium: { badge: 'bg-amber-300 text-amber-950', bar: '[&_[data-slot=progress-indicator]]:bg-amber-300', label: 'MEDIUM' },
  high: { badge: 'bg-orange-400 text-orange-950', bar: '[&_[data-slot=progress-indicator]]:bg-orange-400', label: 'HIGH' },
  critical: { badge: 'bg-red-400 text-red-950', bar: '[&_[data-slot=progress-indicator]]:bg-red-400', label: 'CRITICAL' },
};

const severityTone = {
  info: 'border-sky-400/20 bg-sky-400/8 text-sky-300',
  low: 'border-emerald-400/20 bg-emerald-400/8 text-emerald-300',
  medium: 'border-amber-400/20 bg-amber-400/8 text-amber-300',
  high: 'border-orange-400/20 bg-orange-400/8 text-orange-300',
  critical: 'border-red-400/20 bg-red-400/8 text-red-300',
};

const actionLabels = { keep: '현재 유지', fix: '먼저 수정', purchase: '교체 검토' } as const;
const actionTone = {
  keep: 'border-emerald-400/20 text-emerald-300',
  fix: 'border-sky-400/20 text-sky-300',
  purchase: 'border-orange-400/20 text-orange-300',
} as const;

const sourceStatus = {
  collected: { label: '수집 완료', detail: '진단에 반영됨', tone: 'text-emerald-300' },
  permission_required: { label: '관리자 권한 필요', detail: '관리자로 다시 실행하면 확인 가능', tone: 'text-amber-300' },
  unavailable: { label: '확인하지 못함', detail: '미지원 또는 수집 실패', tone: 'text-red-300' },
  not_in_scope: { label: '기본 진단 미포함', detail: 'Advanced Scan에서 확인', tone: 'text-muted-foreground' },
} as const;

function ResourceIcon({ resourceKey }: { resourceKey: string }) {
  if (resourceKey.includes('cpu')) return <Cpu className="size-4 text-sky-300" />;
  if (resourceKey.includes('memory')) return <MemoryStick className="size-4 text-sky-300" />;
  return <HardDrive className="size-4 text-sky-300" />;
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

export default function Home() {
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(diagnosticsConfig.demoMode ? demoDiagnosis : null);
  const [diagnosisSource, setDiagnosisSource] = useState<'demo' | 'agent'>('demo');
  const [health, setHealth] = useState<AgentHealth | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>('checking');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'findings' | 'inventory' | 'sources'>('findings');

  useEffect(() => {
    let active = true;
    async function hydrate() {
      try {
        const [nextHealth, latest] = await Promise.all([getAgentHealth(), getLatestDiagnosis()]);
        if (!active) return;
        setHealth(nextHealth);
        if (latest) {
          setDiagnosis(latest);
          setDiagnosisSource('agent');
          setConnectionState('live');
        } else if (diagnosticsConfig.demoMode) {
          setDiagnosis(demoDiagnosis);
          setDiagnosisSource('demo');
          setConnectionState('demo');
        } else {
          setDiagnosis(null);
          setConnectionState('empty');
        }
      } catch {
        if (!active) return;
        setHealth(null);
        if (diagnosticsConfig.demoMode) {
          setDiagnosis(demoDiagnosis);
          setDiagnosisSource('demo');
          setConnectionState('demo');
        } else {
          setDiagnosis(null);
          setConnectionState('offline');
        }
      }
    }

    void hydrate();

    return () => { active = false; };
  }, []);

  async function runScan() {
    setRunning(true);
    setError('');
    try {
      const value = await runBasicScan();
      setDiagnosis(value);
      setDiagnosisSource('agent');
      setConnectionState('live');
      const nextHealth = await getAgentHealth().catch(() => null);
      if (nextHealth) setHealth(nextHealth);
    } catch (cause) {
      if (cause instanceof DiagnosticsApiError && cause.status === 404) {
        setDiagnosis(null);
        setConnectionState('empty');
        return;
      }
      setError(cause instanceof Error ? cause.message : 'SpecCheck Backend에 연결할 수 없습니다.');
      setHealth(null);
      setConnectionState('error');
    } finally {
      setRunning(false);
    }
  }

  const tone = diagnosis ? riskTone[diagnosis.risk.level] : riskTone.low;
  const primaryFinding = diagnosis?.findings[0];
  const hasIncompleteSources = diagnosis?.sources.some((source) => source.status !== 'collected' && source.status !== 'not_in_scope') ?? false;
  const categoryItems = [
    { key: 'hardware' as const, label: '하드웨어', icon: <Cpu className="size-4" /> },
    { key: 'software' as const, label: '소프트웨어', icon: <Activity className="size-4" /> },
    { key: 'security' as const, label: '보안', icon: <ShieldCheck className="size-4" /> },
  ];

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-white/8 bg-[#0b1018]/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1480px] items-center justify-between px-5 lg:px-8">
          <div className="flex items-center gap-3">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-[0_0_30px_rgba(45,212,191,.18)]">
              <Radar className="size-5" />
            </span>
            <div>
              <div className="text-sm font-semibold tracking-[0.02em]">SpecCheck</div>
              <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">Diagnostics Agent</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
              <span className={`size-1.5 rounded-full ${connectionState === 'live' ? 'bg-emerald-400 shadow-[0_0_10px_#34d399]' : connectionState === 'empty' ? 'bg-amber-300' : connectionState === 'error' || connectionState === 'offline' ? 'bg-red-400' : 'bg-zinc-500'}`} />
              {connectionState === 'checking' ? 'Backend 확인 중' : connectionState === 'live' && health ? health.agentVersion === 'not-connected' ? `Backend v${health.backendVersion}` : `Agent v${health.agentVersion}` : connectionState === 'empty' && health ? `Backend v${health.backendVersion} · 데이터 없음` : connectionState === 'error' || connectionState === 'offline' ? 'Backend 연결 오류' : 'Demo mode'}
            </span>
            <Button onClick={runScan} disabled={running} size="lg" className="rounded-xl px-4">
              {running ? <RefreshCw className="animate-spin" data-icon="inline-start" /> : <ScanLine data-icon="inline-start" />}
              {running ? '확인 중…' : diagnosis ? '진단 새로고침' : '최신 진단 확인'}
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1480px] px-5 py-7 lg:px-8">
        {error && (
          <Alert variant="destructive" className="mb-5 border-red-400/20 bg-red-400/5">
            <WifiOff />
            <AlertTitle>SpecCheck Backend 연결 실패</AlertTitle>
            <AlertDescription>{error} · 터미널에서 <code className="font-mono text-xs">pnpm dev:all</code>을 실행하세요.</AlertDescription>
          </Alert>
        )}

        {!diagnosis ? (
          <section className="grid min-h-[calc(100vh-10rem)] place-items-center border-y border-white/8 py-16">
            <div className="max-w-xl text-center">
              <span className="mx-auto grid size-12 place-items-center rounded-lg border border-white/10 bg-white/[.03]">
                {connectionState === 'checking' ? <RefreshCw className="size-5 animate-spin text-muted-foreground" /> : <Database className="size-5 text-muted-foreground" />}
              </span>
              <h1 className="mt-5 text-2xl font-semibold">{connectionState === 'checking' ? '진단 데이터 확인 중' : '진단 데이터가 없습니다'}</h1>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                {connectionState === 'checking'
                  ? 'Local Backend와 저장된 Snapshot을 확인하고 있습니다.'
                  : connectionState === 'offline' || connectionState === 'error'
                    ? 'Backend에 연결되지 않았습니다. 서버를 실행한 뒤 다시 확인하세요.'
                    : '고정된 예시 대신 Local Agent가 수집한 실제 Snapshot만 표시합니다.'}
              </p>
              {connectionState !== 'checking' && (
                <>
                  <div className="mt-6 space-y-2 border-y border-white/8 py-4 text-left font-mono text-xs text-muted-foreground">
                    <div><span className="mr-3 text-foreground">1</span>pnpm dev:all</div>
                    <div><span className="mr-3 text-foreground">2</span>cd agent</div>
                    <div><span className="mr-3 text-foreground">3</span>python -m speccheck_agent scan --upload</div>
                  </div>
                  <Button onClick={runScan} disabled={running} className="mt-6">
                    {running ? <RefreshCw className="animate-spin" data-icon="inline-start" /> : <RefreshCw data-icon="inline-start" />}
                    다시 확인
                  </Button>
                </>
              )}
            </div>
          </section>
        ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_350px]">
          <section className="space-y-6">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-primary">Local diagnostics</p>
                <h1 className="text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">현재 PC 상태</h1>
                <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  <span>{formatTime(diagnosis.generatedAt)} · {diagnosis.machine.name}</span>
                  <Badge variant="outline" className={diagnosisSource === 'agent' ? 'border-emerald-400/20 text-emerald-300' : 'border-white/10 text-muted-foreground'}>
                    {diagnosisSource === 'agent' ? 'AGENT DATA' : 'DEMO DATA'}
                  </Badge>
                </p>
              </div>
              <Badge variant="outline" className={`h-7 px-3 ${severityTone[diagnosis.categories.hardware.highestSeverity]}`}>
                {diagnosis.risk.score >= 40 ? <TriangleAlert /> : <Check />}
                {diagnosis.risk.score >= 40 ? '주의 필요' : '정상'}
              </Badge>
            </div>

            <Card className="border border-white/6 bg-card/75 shadow-2xl shadow-black/15">
              <CardHeader className="border-b border-white/6 pb-4">
                <CardTitle>시스템 상태</CardTitle>
                <CardDescription>성능 카운터 · 저장장치 상태</CardDescription>
                <CardAction><Gauge className="size-5 text-primary" /></CardAction>
              </CardHeader>
              <CardContent className="grid gap-4 pt-1 sm:grid-cols-3">
                {diagnosis.resources.map((resource) => (
                  <div key={resource.key} className="min-h-36 space-y-3 rounded-lg border border-white/6 bg-white/[.025] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="flex items-center gap-2 text-sm font-medium">
                        <ResourceIcon resourceKey={resource.key} />{resource.label}
                      </span>
                      <span className="truncate font-mono text-[11px] text-muted-foreground">{resource.detail}</span>
                    </div>
                    <div className="flex items-end justify-between">
                      <strong className="text-2xl font-semibold tracking-tight">{resource.value}{resource.unit}</strong>
                      <span className={`text-[11px] ${resource.status === 'normal' ? 'text-emerald-300' : 'text-amber-300'}`}>
                        {resource.status === 'normal' ? '정상 범위' : '추적 필요'}
                      </span>
                    </div>
                    {resource.unit === '%' && <Progress value={resource.value} className={resource.status === 'normal' ? '[&_[data-slot=progress-indicator]]:bg-sky-400' : '[&_[data-slot=progress-indicator]]:bg-amber-300'} />}
                  </div>
                ))}
              </CardContent>
            </Card>

            <div className="grid gap-4 md:grid-cols-3">
              {categoryItems.map(({ key, label, icon }) => (
                <Card key={key} className="border border-white/6 bg-card/55">
                  <CardHeader>
                    <CardDescription className="flex items-center gap-2">{icon}{label}</CardDescription>
                    <CardTitle className="text-3xl">{diagnosis.categories[key].count}</CardTitle>
                  </CardHeader>
                  <CardContent className="text-xs text-muted-foreground">{diagnosis.categories[key].summary}</CardContent>
                </Card>
              ))}
            </div>

            <div className="space-y-4">
              <div role="tablist" aria-label="진단 상세" className="flex w-fit gap-1 border-b border-white/8 text-sm">
                {[
                  ['findings', '진단 결과'],
                  ['inventory', '하드웨어 정보'],
                  ['sources', '수집 출처'],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === value}
                    onClick={() => setActiveTab(value as typeof activeTab)}
                    className={`relative px-3 py-2 text-sm font-medium transition-colors ${activeTab === value ? 'text-foreground after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-primary' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {activeTab === 'findings' && <div role="tabpanel" className="space-y-3">
                {diagnosis.findings.length === 0 ? (
                  <Alert className={hasIncompleteSources ? 'border-amber-400/15 bg-amber-400/5' : 'border-emerald-400/15 bg-emerald-400/5'}>
                    {hasIncompleteSources ? <Info /> : <Check />}
                    <AlertTitle>{hasIncompleteSources ? '확인된 범위에서 이상 없음' : '이상 징후 없음'}</AlertTitle>
                    <AlertDescription>{hasIncompleteSources ? '일부 항목은 수집되지 않아 정상 여부를 판단하지 않았습니다.' : '현재 Basic Scan 범위에서 Finding이 생성되지 않았습니다.'}</AlertDescription>
                  </Alert>
                ) : diagnosis.findings.map((finding) => (
                  <Card key={finding.id} className="border border-white/6 bg-card/60">
                    <CardHeader>
                      <CardTitle>{finding.title}</CardTitle>
                      <CardDescription>{finding.summary}</CardDescription>
                      <CardAction className="flex items-center gap-2">
                        <Badge variant="outline" className={actionTone[finding.recommendedAction]}>{actionLabels[finding.recommendedAction]}</Badge>
                        <Badge variant="outline" className={severityTone[finding.severity]}>{finding.severity.toUpperCase()} · {Math.round(finding.confidence * 100)}%</Badge>
                      </CardAction>
                    </CardHeader>
                    <CardContent className="grid gap-4 sm:grid-cols-3">
                      <div>
                        <div className="mb-2 text-xs font-semibold text-foreground">근거</div>
                        <ul className="space-y-1.5 text-xs leading-5 text-muted-foreground">
                          {finding.evidence.map((item) => <li key={item}>· {item}</li>)}
                        </ul>
                      </div>
                      <div>
                        <div className="mb-2 text-xs font-semibold text-foreground">원인 후보</div>
                        <ul className="space-y-1.5 text-xs leading-5 text-muted-foreground">
                          {finding.rootCauseCandidates.length ? finding.rootCauseCandidates.map((item) => <li key={item}>· {item}</li>) : <li>제공된 원인 후보 없음</li>}
                        </ul>
                      </div>
                      <div>
                        <div className="mb-2 text-xs font-semibold text-foreground">권장 조치</div>
                        <ul className="space-y-1.5 text-xs leading-5 text-muted-foreground">
                          {finding.actions.length ? finding.actions.map((item) => <li key={item}>· {item}</li>) : <li>추가 조치 없음</li>}
                        </ul>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>}
              {activeTab === 'inventory' && <div role="tabpanel">
                <Card className="border border-white/6 bg-card/60 py-2">
                  <CardContent>
                    <Table>
                      <TableHeader><TableRow><TableHead>분류</TableHead><TableHead>장치</TableHead><TableHead>세부 정보</TableHead><TableHead>상태</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {diagnosis.inventory.map((item) => (
                          <TableRow key={`${item.kind}-${item.name}`}>
                            <TableCell className="font-mono text-xs text-muted-foreground">{item.kind}</TableCell>
                            <TableCell className="font-medium">{item.name}</TableCell>
                            <TableCell className="text-muted-foreground">{item.detail}</TableCell>
                            <TableCell><Badge variant="outline" className={item.status === 'normal' ? 'border-emerald-400/20 text-emerald-300' : 'border-amber-400/20 text-amber-300'}>{item.status}</Badge></TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </div>}
              {activeTab === 'sources' && <div role="tabpanel">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {diagnosis.sources.map((source) => (
                    <Card key={source.name} size="sm" className="border border-white/6 bg-card/60">
                      <CardHeader>
                        <CardDescription className="font-mono uppercase">{source.name}</CardDescription>
                        <CardTitle className="flex items-center gap-2">
                          {source.status === 'collected' ? <Check className="size-4 text-emerald-300" /> : <Info className={`size-4 ${sourceStatus[source.status].tone}`} />}
                          {sourceStatus[source.status].label}
                        </CardTitle>
                        <CardDescription>{sourceStatus[source.status].detail}</CardDescription>
                      </CardHeader>
                    </Card>
                  ))}
                </div>
              </div>}
            </div>
          </section>

          <aside className="space-y-4">
            <Card className="border border-amber-300/15 bg-card/80">
              <CardHeader>
                <CardDescription className="flex items-center gap-2">통합 위험도 <Badge variant="outline" className={actionTone[diagnosis.decision.action]}>{actionLabels[diagnosis.decision.action]}</Badge></CardDescription>
                <CardTitle className="text-5xl font-semibold tracking-[-0.05em]">{diagnosis.risk.score}<span className="ml-1 text-lg text-muted-foreground">/100</span></CardTitle>
                <CardAction><Badge className={tone.badge}>{tone.label}</Badge></CardAction>
              </CardHeader>
              <CardContent className="space-y-4">
                <Progress value={diagnosis.risk.score} className={tone.bar} />
                <p className="text-sm leading-6 text-muted-foreground">{diagnosis.risk.summary}</p>
              </CardContent>
            </Card>

            <Card className="border border-primary/15 bg-card/75">
              <CardHeader>
                <CardDescription className="flex items-center gap-2"><Sparkles className="size-4 text-primary" />로컬 AI 진단</CardDescription>
                <CardTitle className="text-base">{diagnosis.ai.provider === 'ollama' ? 'Gemma 진단 설명' : '규칙 기반 진단 설명'}</CardTitle>
                <CardAction>
                  <Badge variant="outline" className={diagnosis.ai.provider === 'ollama' ? 'border-primary/25 text-primary' : 'border-white/10 text-muted-foreground'}>
                    {diagnosis.ai.provider === 'ollama' ? 'LOCAL AI' : 'SAFE FALLBACK'}
                  </Badge>
                </CardAction>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm leading-6 text-muted-foreground">{diagnosis.ai.overview}</p>
                <ol className="space-y-2">
                  {diagnosis.ai.actionPlan.map((action, index) => (
                    <li key={action} className="flex gap-2 text-xs leading-5 text-muted-foreground">
                      <span className="grid size-5 shrink-0 place-items-center rounded-full bg-primary/10 font-mono text-[10px] text-primary">{index + 1}</span>
                      {action}
                    </li>
                  ))}
                </ol>
                <div className="flex items-center gap-2 border-t border-white/6 pt-3 text-[10px] text-muted-foreground">
                  <Bot className="size-3.5" /> {diagnosis.ai.model} · PC 외부 전송 없음
                </div>
              </CardContent>
            </Card>

            {primaryFinding && (
              <Card className="border border-white/6 bg-card/65">
                <CardHeader>
                  <CardDescription>우선 확인 항목</CardDescription>
                  <CardTitle>{primaryFinding.title}</CardTitle>
                  <CardAction><HardDrive className="size-5 text-amber-300" /></CardAction>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="rounded-lg bg-white/[.035] p-3">
                    <div className="font-medium">신뢰도 {Math.round(primaryFinding.confidence * 100)}%</div>
                    <p className="mt-1 leading-5 text-muted-foreground">{primaryFinding.rootCauseCandidates.join(' · ')}</p>
                  </div>
                </CardContent>
              </Card>
            )}

            <div className="flex items-center justify-between px-1 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1.5"><Database className="size-3" />SQLite local history</span>
              <span>Schema {diagnosis.schemaVersion}</span>
            </div>
          </aside>
        </div>
        )}
      </div>
    </main>
  );
}
