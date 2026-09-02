import { gemmaConfig } from './config.mjs';

function fallbackExplanation(diagnosis) {
  const primary = diagnosis.findings[0];
  return {
    provider: 'template',
    model: 'deterministic-ko-v1',
    status: 'fallback',
    overview: primary
      ? `${primary.title} 항목이 가장 우선입니다. ${primary.summary}`
      : '현재 Basic Scan 범위에서 즉시 조치가 필요한 이상은 확인되지 않았습니다.',
    actionPlan: primary?.actions?.slice(0, 3) ?? ['정기적으로 Basic Scan을 다시 실행하세요.'],
  };
}

function safeLocalUrl(raw) {
  const url = new URL(raw || gemmaConfig.baseUrl);
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)) {
    throw new Error('Gemma endpoint must be loopback-only');
  }
  return url.origin;
}

export class GemmaClient {
  constructor(options = {}) {
    this.baseUrl = safeLocalUrl(options.baseUrl ?? gemmaConfig.baseUrl);
    this.model = options.model ?? gemmaConfig.model;
    this.timeoutMs = Number(options.timeoutMs ?? gemmaConfig.timeoutMs);
    this.statusTimeoutMs = Number(options.statusTimeoutMs ?? gemmaConfig.statusTimeoutMs);
    this.temperature = Number(options.temperature ?? gemmaConfig.temperature);
    this.maxTokens = Number(options.maxTokens ?? gemmaConfig.maxTokens);
  }

  async status() {
    try {
      const response = await fetch(`${this.baseUrl}/api/tags`, { signal: AbortSignal.timeout(this.statusTimeoutMs) });
      if (!response.ok) throw new Error(`Ollama returned ${response.status}`);
      const payload = await response.json();
      return {
        available: true,
        model: this.model,
        installed: Boolean(payload.models?.some((item) => item.name === this.model || item.model === this.model)),
      };
    } catch {
      return { available: false, model: this.model, installed: false };
    }
  }

  async explain(diagnosis) {
    const fallback = fallbackExplanation(diagnosis);
    try {
      const compact = {
        risk: diagnosis.risk,
        findings: diagnosis.findings.map(({ title, severity, summary, evidence, rootCauseCandidates, actions }) => ({
          title, severity, summary, evidence, rootCauseCandidates, actions,
        })),
      };
      const response = await fetch(`${this.baseUrl}/api/chat`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        signal: AbortSignal.timeout(this.timeoutMs),
        body: JSON.stringify({
          model: this.model,
          stream: false,
          format: 'json',
          options: { temperature: this.temperature, num_predict: this.maxTokens },
          messages: [
            {
              role: 'system',
              content: '당신은 Windows PC 진단 설명기다. 제공된 사실만 사용하고 과장하지 않는다. JSON으로 overview 문자열과 actionPlan 문자열 배열만 답한다.',
            },
            { role: 'user', content: JSON.stringify(compact) },
          ],
        }),
      });
      if (!response.ok) throw new Error(`Ollama returned ${response.status}`);
      const payload = await response.json();
      const parsed = JSON.parse(payload.message?.content ?? '{}');
      if (typeof parsed.overview !== 'string' || !Array.isArray(parsed.actionPlan)) throw new Error('Invalid Gemma response');
      return {
        provider: 'ollama',
        model: this.model,
        status: 'generated',
        overview: parsed.overview.slice(0, 1200),
        actionPlan: parsed.actionPlan.filter((item) => typeof item === 'string').slice(0, 5),
      };
    } catch {
      return fallback;
    }
  }
}
