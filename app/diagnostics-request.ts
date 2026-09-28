export class DiagnosticsApiError extends Error {
  readonly status: number;
  readonly code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'DiagnosticsApiError';
    this.status = status;
    this.code = code;
  }
}

export async function requestJson<T>(url: string, init: RequestInit | undefined, timeoutMs: number): Promise<T> {
  const signal = AbortSignal.timeout(timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal });
    let payload: T & { message?: string; detail?: string | Array<{ msg?: string }>; error?: string };
    try {
      payload = await response.json() as typeof payload;
    } catch (error) {
      if (signal.aborted) throw error;
      throw new DiagnosticsApiError('진단 서비스가 올바른 JSON 응답을 반환하지 않았습니다.', response.status, 'INVALID_RESPONSE');
    }
    if (!response.ok) {
      const detail = Array.isArray(payload?.detail)
        ? payload.detail.map(item => item.msg).filter(Boolean).slice(0, 5).join('; ')
        : payload?.detail;
      throw new DiagnosticsApiError(payload?.message ?? detail ?? 'SpecCheck Backend 요청에 실패했습니다.', response.status, payload?.error);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DiagnosticsApiError) throw error;
    if (signal.aborted || (error instanceof Error && (error.name === 'TimeoutError' || error.name === 'AbortError'))) {
      throw new DiagnosticsApiError('응답 대기 시간이 초과됐습니다. 서버에서 처리가 계속될 수 있습니다.', 0, 'REQUEST_TIMEOUT');
    }
    throw new DiagnosticsApiError('진단 서비스에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.', 0, 'NETWORK_ERROR');
  }
}
