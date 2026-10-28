import type { Diagnosis, LocalScanStatus } from './types';

export async function loadScanResult(
  completed: LocalScanStatus,
  readDiagnosis: (scanId: string) => Promise<Diagnosis>,
  readStatus: () => Promise<LocalScanStatus>,
) {
  if (completed.status !== 'completed' || !completed.scanId || !completed.runId) {
    throw new Error('완료된 스캔의 결과 식별자가 없습니다.');
  }
  const diagnosis = await readDiagnosis(completed.scanId);
  if (diagnosis.scanId !== completed.scanId) {
    throw new Error('요청한 스캔과 진단 결과가 일치하지 않습니다.');
  }
  const current = await readStatus();
  return {
    current,
    diagnosis: current.runId === completed.runId && current.status === 'completed'
      && current.scanId === completed.scanId ? diagnosis : null,
  };
}

type MonitorOptions = {
  signal: AbortSignal;
  readStatus: () => Promise<LocalScanStatus>;
  onStatus: (status: LocalScanStatus) => void;
  onConnection: (connected: boolean) => void;
  onFinished: (status: LocalScanStatus) => Promise<void>;
  onResultError?: (error: unknown, status: LocalScanStatus, attempt: number, willRetry: boolean) => void;
  maxResultAttempts?: number;
  intervalMs?: number;
};

function pause(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    if (signal.aborted) return resolve();
    const finish = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', finish);
      resolve();
    };
    const timer = setTimeout(finish, milliseconds);
    signal.addEventListener('abort', finish, { once: true });
  });
}

export async function monitorScan(options: MonitorOptions) {
  let finishedRun: string | null = null;
  let attemptedRun: string | null = null;
  let resultAttempts = 0;
  while (!options.signal.aborted) {
    try {
      const status = await options.readStatus();
      if (options.signal.aborted) return;
      options.onConnection(true);
      options.onStatus(status);
      if (status.runId && status.runId !== finishedRun && (status.status === 'completed' || status.status === 'failed')) {
        if (attemptedRun !== status.runId) {
          attemptedRun = status.runId;
          resultAttempts = 0;
        }
        try {
          await options.onFinished(status);
          finishedRun = status.runId;
        } catch (error) {
          if (options.signal.aborted) return;
          resultAttempts++;
          const willRetry = resultAttempts < (options.maxResultAttempts ?? 3);
          if (!willRetry) finishedRun = status.runId;
          options.onResultError?.(error, status, resultAttempts, willRetry);
        }
        if (options.signal.aborted) return;
      }
    } catch {
      if (options.signal.aborted) return;
      options.onConnection(false);
    }
    await pause(options.intervalMs ?? 1500, options.signal);
  }
}
