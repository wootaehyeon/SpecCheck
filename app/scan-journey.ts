import type { LocalScanStatus } from './types';

export type StepState = 'pending' | 'active' | 'complete' | 'unknown' | 'failed';

export const scanSteps = [
  { label: '권한 승인', owner: 'Windows Agent', detail: 'Windows 관리자 권한 확인' },
  { label: 'PC 정보 수집', owner: 'Windows Agent', detail: '하드웨어·성능·이벤트 수집' },
  { label: '로컬 저장', owner: 'Windows Agent', detail: 'PC에 수집 기록 보관' },
  { label: '서버 전송', owner: '진단 서버', detail: '수집한 스냅샷 전달' },
  { label: '진단 결과', owner: '진단 서버', detail: '근거 분석·권장 조치 제공' },
] as const;

type JourneyOptions = {
  status: LocalScanStatus | null;
  starting: boolean;
  checking: boolean;
  disconnected: boolean;
  loadingResult: boolean;
  resultFailed: boolean;
  resultScanId: string | null;
};

export function scanJourney(options: JourneyOptions): {
  states: StepState[];
  label: string;
  message: string;
  progress: number | null;
} {
  const { status } = options;
  const pending: StepState[] = scanSteps.map(() => 'pending');
  const unknown: StepState[] = scanSteps.map(() => 'unknown');
  if (options.disconnected || options.checking) {
    return { states: unknown, label: '상태 확인 중', progress: null,
      message: options.disconnected ? '연결 복구 후 실제 진행 단계를 다시 확인합니다.' : '진단 서버에서 현재 스캔 상태를 확인하고 있습니다.' };
  }
  if (options.starting) {
    return { states: pending, label: '시작 요청 중', progress: null, message: '진단 서버에 Agent 실행을 요청하고 있습니다.' };
  }
  if (!status || status.status === 'idle') {
    return { states: pending, label: '새 스캔 대기', progress: null, message: 'Agent로 진단을 시작하면 실제 처리 단계가 표시됩니다.' };
  }
  if (status.status === 'failed') {
    return { states: unknown, label: '스캔 중단', progress: null, message: status.message };
  }
  if (status.status === 'completed') {
    const matched = !!status.scanId && status.scanId === options.resultScanId;
    const last: StepState = options.resultFailed ? 'failed' : options.loadingResult ? 'active' : matched ? 'complete' : 'pending';
    return {
      states: ['complete', 'complete', 'complete', 'complete', last],
      label: options.resultFailed ? '결과 조회 실패' : options.loadingResult ? '서버 진단·결과 조회 중' : matched ? '진단 결과 확인 완료' : '진단 결과 대기',
      message: options.resultFailed ? '수집과 전송은 완료됐습니다. 진단 결과를 다시 불러와주세요.'
        : options.loadingResult ? '서버에 진단 결과를 요청하고 해당 스캔의 결과인지 확인하고 있습니다.'
        : matched ? '이번 스캔의 수집 정보와 서버 진단 결과를 확인했습니다.' : '수집과 서버 전송이 완료됐습니다. 진단 결과 확인을 기다립니다.',
      // Agent의 100%는 수집·전송 완료이며 서버 진단 진행률은 제공되지 않는다.
      progress: null,
    };
  }
  const phaseIndex: Partial<Record<LocalScanStatus['phase'], number>> = { permission: 0, collecting: 1, saving: 2, uploading: 3 };
  const current = phaseIndex[status.phase];
  if (current === undefined) {
    return { states: unknown, label: '진행 단계 확인 중', message: status.message, progress: null };
  }
  return {
    states: scanSteps.map((_, index) => index < current ? 'complete' : index === current ? 'active' : 'pending'),
    label: `${scanSteps[current].label} 중`,
    message: status.message,
    progress: status.progress,
  };
}
