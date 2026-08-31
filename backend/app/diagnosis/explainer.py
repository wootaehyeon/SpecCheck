"""진단 결과의 자연어 설명 (Phase 4 / M5).

로컬 우선 원칙에 따라 기본 백엔드는 Local Gemma(Ollama)다. 모델이 없으면
템플릿으로 자동 대체되므로, 설명 기능 때문에 진단이 실패하는 일은 없다.

설계 규약: **LLM은 판정하지 않는다.** 규칙 엔진이 이미 만든 Finding을
읽기 쉬운 문장으로 옮기기만 한다. 프롬프트에 telemetry 원본을 넣지 않고
확정된 Finding만 넣는 이유가 이것이다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from app.core.config import get_settings
from app.schemas.diagnosis import ActionType, DiagnosisResult

_ACTION_LABEL = {
    ActionType.KEEP: "유지한다",
    ActionType.FIX: "수정한다",
    ActionType.PURCHASE: "구매한다",
}

SYSTEM_PROMPT = (
    "당신은 PC 진단 결과를 초보자에게 설명하는 전문가입니다. "
    "주어진 진단 항목만 사용해 설명하고, 주어지지 않은 원인이나 부품을 추측해 말하지 마세요. "
    "사용자가 돈을 쓰지 않아도 되는 경우라면 그 점을 분명히 알려주세요."
)


def explain(result: DiagnosisResult) -> str:
    """진단 결과를 자연어로 설명한다. 실패해도 예외를 던지지 않는다."""
    settings = get_settings()
    if not settings.llm_enabled:
        return render_template(result)

    try:
        return _ask_ollama(
            build_prompt(result),
            base_url=settings.ollama_url,
            model=settings.llm_model,
            timeout=settings.llm_timeout,
        )
    except Exception:
        # 설명은 부가 기능이다. 실패하면 템플릿으로 조용히 내려앉는다.
        return render_template(result)


def build_prompt(result: DiagnosisResult) -> str:
    lines = [
        "다음은 사용자 PC의 진단 결과입니다.",
        "",
        "[종합 판정] {0}".format(_ACTION_LABEL[result.decision.action]),
        "[판정 근거] {0}".format(result.decision.reason),
        "[진단 신뢰도] {0}".format(result.confidence),
        "",
        "[발견된 항목]",
    ]
    if not result.findings:
        lines.append("- 없음")
    for finding in result.findings:
        lines.append("- ({0}/{1}) {2}".format(finding.axis.value, finding.severity.value, finding.title))
        lines.append("  현상: {0}".format(finding.summary))
        if finding.root_cause:
            lines.append("  원인: {0}".format(finding.root_cause))
        if finding.action_detail:
            lines.append("  조치: {0}".format(finding.action_detail))

    lines += [
        "",
        "위 내용을 바탕으로 3~5문장으로 설명해 주세요.",
        "1) 지금 PC 상태가 어떤지 2) 왜 그런지 3) 무엇을 하면 되는지 순서로 씁니다.",
    ]
    return "\n".join(lines)


def render_template(result: DiagnosisResult) -> str:
    """LLM 없이 만드는 결정적 설명. 테스트와 폴백 양쪽에 쓴다."""
    action = _ACTION_LABEL[result.decision.action]

    if not result.findings:
        return (
            "종합 판정: {0}\n{1}\n"
            "확보한 항목: {2}".format(
                action,
                result.decision.reason,
                ", ".join(result.coverage) or "없음",
            )
        )

    lines = ["종합 판정: {0}".format(action), result.decision.reason, ""]
    for index, finding in enumerate(result.findings, start=1):
        lines.append("{0}. [{1}] {2}".format(index, finding.severity.value.upper(), finding.title))
        lines.append("   {0}".format(finding.summary))
        if finding.root_cause:
            lines.append("   원인: {0}".format(finding.root_cause))
        if finding.action_detail:
            lines.append("   조치: {0}".format(finding.action_detail))
    return "\n".join(lines)


def _ask_ollama(prompt: str, base_url: str, model: str, timeout: float) -> str:
    """Ollama ``/api/generate`` 호출 (스트리밍 없이 한 번에 받는다)."""
    body = json.dumps(
        {
            "model": model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    text = (payload.get("response") or "").strip()
    if not text:
        raise RuntimeError("LLM이 빈 응답을 반환했습니다")
    return text
