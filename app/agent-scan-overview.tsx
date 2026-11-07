import { Check, Cpu, Database, FileCheck2, HardDrive, Info, RefreshCw, Server, ShieldCheck, TriangleAlert, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { scanJourney, scanSteps, type StepState } from './scan-journey';
import type { Diagnosis, LocalScanStatus } from './types';

const stepIcons = [ShieldCheck, Cpu, Database, Upload, FileCheck2];
const stepLabels: Record<StepState, string> = { pending: '대기', active: '진행 중', complete: '완료', unknown: '미확인', failed: '조회 실패' };
const stepTones: Record<StepState, string> = {
  pending: 'border-white/8 bg-white/[.015] text-muted-foreground',
  active: 'border-primary/40 bg-primary/8 text-primary',
  complete: 'border-emerald-400/20 bg-emerald-400/5 text-emerald-300',
  unknown: 'border-white/8 bg-white/[.015] text-muted-foreground',
  failed: 'border-red-400/25 bg-red-400/5 text-red-300',
};

export const sourceNames = { wmi: '하드웨어 · WMI', cim: '하드웨어 · CIM', whea: '시스템 이벤트 · WHEA', storage: '저장장치 상태', performance: '성능 카운터', sysmon: '보안 이벤트 · Sysmon' } as const;

function timestamp(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return '확인하지 못함';
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value));
}

export function AgentScanJourney(props: {
  status: LocalScanStatus | null;
  starting: boolean;
  checking: boolean;
  disconnected: boolean;
  loadingResult: boolean;
  resultFailed: boolean;
  resultScanId: string | null;
}) {
  const journey = scanJourney(props);
  return (
    <section aria-label="Agent에서 서버 진단까지" className="mb-6 rounded-xl border border-white/10 bg-card/60 p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><Server className="size-4 text-primary" />Agent → 서버 → 진단 결과</h2>
        <output className="text-xs text-primary">{journey.label}</output>
      </div>
      <ol className="grid gap-2 sm:grid-cols-5">
        {scanSteps.map((step, index) => {
          const state = journey.states[index];
          const Icon = state === 'complete' ? Check : state === 'active' ? RefreshCw : state === 'failed' ? TriangleAlert : stepIcons[index];
          return (
            <li key={step.label} aria-current={state === 'active' ? 'step' : undefined} className={`flex gap-3 rounded-lg border p-3 sm:block ${stepTones[state]}`}>
              <Icon aria-hidden="true" className={`size-4 shrink-0 sm:mb-3 ${state === 'active' ? 'animate-spin motion-reduce:animate-none' : ''}`} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-1 text-xs font-semibold"><span>{step.label}</span><span className="text-[10px] font-normal">{stepLabels[state]}</span></div>
                <p className="mt-1 text-[10px] text-muted-foreground">{step.owner}</p>
                <p className="mt-2 text-[11px] leading-5 text-muted-foreground">{step.detail}</p>
              </div>
            </li>
          );
        })}
      </ol>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs leading-5 text-muted-foreground">
        <p>{journey.message}</p>
        {journey.progress !== null && <span className="font-mono">수집·전송 {journey.progress}%</span>}
      </div>
      {journey.progress !== null && <Progress aria-label="Agent 수집·전송 진행률" value={journey.progress} className="mt-3 [&_[data-slot=progress-indicator]]:bg-primary" />}
    </section>
  );
}

export function AgentScanEvidence({ diagnosis, isDemo, previous }: { diagnosis: Diagnosis; isDemo: boolean; previous: boolean }) {
  const collected = diagnosis.sources.filter(source => source.status === 'collected');
  const times = collected.flatMap(source => source.collectedAt && !Number.isNaN(Date.parse(source.collectedAt)) ? [source.collectedAt] : []);
  const collectedAt = times.sort((a, b) => Date.parse(b) - Date.parse(a))[0] ?? null;
  return (
    <section aria-label="수집과 진단 기록" className="rounded-xl border border-primary/15 bg-primary/[.025] p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold"><FileCheck2 className="size-4 text-primary" />수집과 진단 기록</h2>
        <Badge variant="outline" className={isDemo ? 'text-muted-foreground' : 'border-primary/20 text-primary'}>{isDemo ? '예시 데이터' : previous ? '이전 스캔 기록' : '실제 Agent 수집 기록'}</Badge>
      </div>
      <dl className="mt-4 grid gap-4 text-xs sm:grid-cols-3">
        <div><dt className="text-muted-foreground">Agent 수집 시각</dt><dd className="mt-1.5 font-medium">{timestamp(collectedAt)}</dd></div>
        <div><dt className="text-muted-foreground">서버 진단 생성 시각</dt><dd className="mt-1.5 font-medium">{timestamp(diagnosis.generatedAt)}</dd></div>
        <div><dt className="text-muted-foreground">수집 완료 출처</dt><dd className="mt-1.5 font-medium">{collected.length} / {diagnosis.sources.length}개 · Agent {diagnosis.machine.agentVersion}</dd></div>
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        {diagnosis.sources.map(source => (
          <span key={source.name} className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] ${source.status === 'collected' ? 'border-emerald-400/15 text-emerald-300' : 'border-white/10 text-muted-foreground'}`}>
            {source.status === 'collected' ? <Check aria-hidden="true" className="size-3" /> : <Info aria-hidden="true" className="size-3" />}
            {sourceNames[source.name]} · {source.status === 'collected' ? '수집 완료' : source.status === 'permission_required' ? '권한 필요' : source.status === 'not_in_scope' ? '미포함' : '확인 못함'}
          </span>
        ))}
      </div>
      <details className="mt-4 border-t border-white/8 pt-3">
        <summary className="cursor-pointer text-xs font-medium text-primary">진단에 사용된 근거 확인 · {diagnosis.findings.length}개 진단 항목</summary>
        <div className="mt-3 space-y-3">
          {diagnosis.findings.length ? diagnosis.findings.map(finding => (
            <div key={finding.id}>
              <p className="text-xs font-medium">{finding.title} <span className="font-mono text-[10px] text-muted-foreground">{finding.code}</span></p>
              {finding.evidence.length ? <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-5 text-muted-foreground">{finding.evidence.map((evidence, index) => <li key={index}>{evidence}</li>)}</ul> : <p className="mt-1 text-xs text-muted-foreground">제공된 세부 근거가 없습니다.</p>}
            </div>
          )) : <p className="text-xs leading-5 text-muted-foreground">수집된 범위에서 규칙이 감지한 이상 징후가 없습니다. 수집하지 못한 항목의 정상 여부는 판단하지 않습니다.</p>}
          <p className="break-all font-mono text-[10px] text-muted-foreground">스캔 ID: {diagnosis.scanId}</p>
        </div>
      </details>
    </section>
  );
}

export function AgentCollectionItems() {
  return (
    <ul aria-label="Agent 수집 항목" className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground">
      <li className="flex items-center gap-1.5"><Cpu className="size-3.5 text-primary" />하드웨어 사양</li>
      <li className="flex items-center gap-1.5"><Server className="size-3.5 text-primary" />CPU·메모리 성능</li>
      <li className="flex items-center gap-1.5"><HardDrive className="size-3.5 text-primary" />저장장치 상태</li>
      <li className="flex items-center gap-1.5"><ShieldCheck className="size-3.5 text-primary" />시스템·보안 이벤트</li>
    </ul>
  );
}
