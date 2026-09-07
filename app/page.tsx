'use client';

import { useEffect, useState } from 'react';
import {
  Activity,
  Bot,
  Check,
  Cpu,
  Database,
  ExternalLink,
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
import { getAgentHealth, getBasicScanStatus, getLatestDiagnosis, getMarketPrices, startBasicScan } from './diagnostics-client';
import { demoDiagnosis } from './fixtures/demo-diagnosis';
import type { AgentHealth, Diagnosis, LocalScanStatus, MarketPrice } from './types';

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

const recommendationTone = {
  normal: 'border-sky-400/20 text-sky-300',
  high: 'border-orange-400/20 text-orange-300',
  urgent: 'border-red-400/20 text-red-300',
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

function formatPrice(value: number) {
  return new Intl.NumberFormat('ko-KR', { style: 'currency', currency: 'KRW', maximumFractionDigits: 0 }).format(value);
}

function delay(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function CandidateComparison({ diagnosis, marketPrices, marketLoading }: {
  diagnosis: Diagnosis;
  marketPrices: Record<string, MarketPrice>;
  marketLoading: boolean;
}) {
  if (diagnosis.recommendations.length === 0) return null;

  return <Card className="border border-orange-400/15 bg-card/65">
    <CardHeader>
      <CardDescription>진단 근거 기반 호환성 검증</CardDescription>
      <CardTitle>문제 부품 중심 교체 제안</CardTitle>
      <CardAction><HardDrive className="size-5 text-orange-300" /></CardAction>
    </CardHeader>
    <CardContent className="space-y-6">
      {diagnosis.recommendations.map((recommendation) => (
        <section key={recommendation.id} className="border-t border-white/6 pt-5 first:border-t-0 first:pt-0">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-medium">{recommendation.title}</div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{recommendation.description}</p>
            </div>
            <Badge variant="outline" className={recommendationTone[recommendation.priority]}>{recommendation.priority.toUpperCase()}</Badge>
          </div>
          <div className="mb-4 border-l-2 border-primary/35 pl-3">
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold">
              <Sparkles className="size-3.5 text-primary" />
              <span>교체 추천 AI</span>
              <Badge variant="outline" className="text-[9px]">
                {recommendation.aiInsight.status === 'generated'
                  ? 'LOCAL GEMMA'
                  : recommendation.aiInsight.status === 'unavailable'
                    ? 'GEMMA UNAVAILABLE'
                    : 'RULE FALLBACK'}
              </Badge>
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">{recommendation.aiInsight.rationale}</p>
            {recommendation.aiInsight.cautions.length > 0 && <ul className="mt-2 space-y-1 text-[10px] leading-4 text-muted-foreground">
              {recommendation.aiInsight.cautions.map((item) => <li key={item}>주의 · {item}</li>)}
            </ul>}
            <div className="mt-2 font-mono text-[9px] text-muted-foreground">{recommendation.aiInsight.model} · PC 외부 전송 없음</div>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {(recommendation.candidates ?? []).map((candidate) => {
              const priced = candidate.parts.map((part) => marketPrices[part.key]).filter(Boolean);
              const completePrice = candidate.parts.length > 0 && priced.length === candidate.parts.length && priced.every((item) => !item.error && item.averagePrice > 0);
              const lowestTotal = completePrice ? priced.reduce((sum, item) => sum + item.lowestPrice, 0) : null;
              const marketError = priced.find((item) => item.error)?.error;
              return <div key={candidate.id} className={`rounded-lg border p-4 ${candidate.recommended ? 'border-primary/25 bg-primary/[.04]' : 'border-white/8 bg-white/[.02]'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold">{candidate.title}</h3>
                      {candidate.recommended && <Badge className="bg-primary text-primary-foreground">권장</Badge>}
                    </div>
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">{candidate.summary}</p>
                  </div>
                  <Badge variant="outline" className={candidate.compatibilityStatus === 'passed' ? 'border-emerald-400/20 text-emerald-300' : 'border-amber-400/20 text-amber-300'}>
                    {candidate.compatibilityStatus === 'passed' ? '확인 조건 일치' : '추가 확인 필요'}
                  </Badge>
                </div>

                <div className="mt-4 space-y-2">
                  <div className="text-[11px] font-semibold">교체 부품</div>
                  {candidate.parts.map((part) => {
                    const price = marketPrices[part.key];
                    const hasPrice = price && !price.error && price.lowestPrice > 0;
                    return <div key={part.key} className="rounded-md border border-white/6 bg-black/10 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-xs font-medium">{part.name}</div>
                          <div className="mt-1 text-[10px] leading-4 text-muted-foreground">{part.reason}</div>
                          {part.specifications.length > 0 && <div className="mt-2 flex flex-wrap gap-1">
                            {part.specifications.map((specification) => <Badge key={specification} variant="outline" className="text-[9px] font-normal text-muted-foreground">{specification}</Badge>)}
                          </div>}
                        </div>
                        {hasPrice && <div className="shrink-0 text-xs font-semibold text-primary">최저 {formatPrice(price.lowestPrice)}</div>}
                      </div>
                      {hasPrice && <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground">
                        <span>{price.mall} · {price.listingCount}건 비교 · 평균 {formatPrice(price.averagePrice)}</span>
                        {price.purchaseLink && <a href={price.purchaseLink} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary">최저가 상품 <ExternalLink className="size-3" /></a>}
                      </div>}
                      {part.sourceUrl && <a href={part.sourceUrl} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-[10px] text-primary">
                        {part.sourceLabel ?? '제조사 사양'} <ExternalLink className="size-3" />
                      </a>}
                    </div>;
                  })}
                  {marketLoading && <div className="flex items-center gap-2 text-[10px] text-muted-foreground"><RefreshCw className="size-3 animate-spin" />부품별 시세 확인 중</div>}
                  {!marketLoading && marketError && <div className="text-[10px] leading-4 text-amber-300">{marketError}</div>}
                  {!marketLoading && !completePrice && !marketError && <div className="text-[10px] leading-4 text-muted-foreground">동일 모델의 네이버 쇼핑 최저가를 확인하지 못했습니다.</div>}
                  {lowestTotal !== null && <div className="flex items-center justify-between border-t border-white/8 pt-3 text-sm"><span>예상 최저 합계</span><strong>{formatPrice(lowestTotal)}</strong></div>}
                </div>

                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div>
                    <div className="mb-2 text-[11px] font-semibold">호환성 근거</div>
                    <ul className="space-y-2">
                      {candidate.checks.map((check) => <li key={`${candidate.id}-${check.label}`} className="text-[10px] leading-4 text-muted-foreground">
                        <span className={check.status === 'passed' ? 'text-emerald-300' : 'text-amber-300'}>{check.status === 'passed' ? '통과' : '확인 필요'}</span> · {check.detail}
                      </li>)}
                    </ul>
                  </div>
                  <div>
                    <div className="mb-2 text-[11px] font-semibold">비교 근거</div>
                    <ul className="space-y-2 text-[10px] leading-4 text-muted-foreground">
                      {candidate.tradeoffs.map((item) => <li key={item}>· {item}</li>)}
                    </ul>
                  </div>
                </div>
              </div>;
            })}
          </div>
          <div className="mt-3 font-mono text-[10px] text-muted-foreground">판정 근거: {recommendation.findingIds.join(', ')}</div>
        </section>
      ))}
    </CardContent>
  </Card>;
}

export default function Home() {
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(diagnosticsConfig.demoMode ? demoDiagnosis : null);
  const [diagnosisSource, setDiagnosisSource] = useState<'demo' | 'agent'>('demo');
  const [health, setHealth] = useState<AgentHealth | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>('checking');
  const [running, setRunning] = useState(false);
  const [scanStatus, setScanStatus] = useState<LocalScanStatus | null>(null);
  const [error, setError] = useState('');
  const [marketPrices, setMarketPrices] = useState<Record<string, MarketPrice>>({});
  const [marketLoading, setMarketLoading] = useState(false);
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

  useEffect(() => {
    let active = true;
    const recommendations = diagnosis?.recommendations ?? [];
    if (recommendations.length === 0) {
      setMarketPrices({});
      setMarketLoading(false);
      return () => { active = false; };
    }

    setMarketLoading(true);
    void getMarketPrices(recommendations)
      .then((response) => {
        if (!active) return;
        setMarketPrices(Object.fromEntries(response.prices.map((item) => [item.key, item])));
      })
      .catch(() => {
        if (active) setMarketPrices({});
      })
      .finally(() => {
        if (active) setMarketLoading(false);
      });

    return () => { active = false; };
  }, [diagnosis?.scanId]);

  async function runScan() {
    setRunning(true);
    setError('');
    try {
      let status = await startBasicScan();
      setScanStatus(status);
      const deadline = Date.now() + 5 * 60_000;
      while (status.status === 'running') {
        if (Date.now() >= deadline) throw new Error('스캔 대기 시간 5분을 초과했습니다.');
        await delay(750);
        status = await getBasicScanStatus();
        setScanStatus(status);
      }
      if (status.status === 'failed') throw new Error(status.message);

      const value = await getLatestDiagnosis();
      if (!value) throw new Error('스캔은 끝났지만 새 진단 결과를 찾지 못했습니다.');
      setDiagnosis(value);
      setDiagnosisSource('agent');
      setConnectionState('live');
      const nextHealth = await getAgentHealth().catch(() => null);
      if (nextHealth) setHealth(nextHealth);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'SpecCheck Backend에 연결할 수 없습니다.');
      if (!diagnosis) setConnectionState('error');
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
              {running ? `${scanStatus?.progress ?? 0}%` : diagnosis ? '다시 스캔' : '기본 진단 시작'}
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1480px] px-5 py-7 lg:px-8">
        {error && (
          <Alert variant="destructive" className="mb-5 border-red-400/20 bg-red-400/5">
            <WifiOff />
            <AlertTitle>기본 진단 실행 실패</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {running && scanStatus && (
          <Alert className="mb-5 border-primary/20 bg-primary/5">
            <RefreshCw className="animate-spin text-primary" />
            <AlertTitle>관리자 Basic Scan 실행 중</AlertTitle>
            <AlertDescription className="space-y-2">
              <span className="block">{scanStatus.message}</span>
              <Progress value={scanStatus.progress} className="[&_[data-slot=progress-indicator]]:bg-primary" />
            </AlertDescription>
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
                <Button onClick={runScan} disabled={running} className="mt-6">
                  {running ? <RefreshCw className="animate-spin" data-icon="inline-start" /> : <ScanLine data-icon="inline-start" />}
                  {running ? `${scanStatus?.progress ?? 0}% 수집 중` : '관리자 스캔 시작'}
                </Button>
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

            <CandidateComparison diagnosis={diagnosis} marketPrices={marketPrices} marketLoading={marketLoading} />

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
