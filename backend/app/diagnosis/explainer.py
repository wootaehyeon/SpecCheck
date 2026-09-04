"""Natural-language explanations for confirmed diagnosis findings.

The LLM never decides whether a system is healthy. It only rewrites findings
already produced by the deterministic rule engine. Failures always fall back
to a local template.
"""

from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlparse

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
    """Return the legacy text explanation used by existing diagnosis routes."""
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
        return render_template(result)


def ollama_status() -> dict:
    """Return local model availability without allowing a remote endpoint."""
    settings = get_settings()
    try:
        base_url = _safe_local_url(settings.ollama_url)
        request = urllib.request.Request(base_url + "/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=settings.llm_status_timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = [item.get("name", "") for item in payload.get("models", [])]
        installed = any(
            name == settings.llm_model or name.startswith(settings.llm_model + ":")
            for name in models
        )
        return {"available": True, "model": settings.llm_model, "installed": installed}
    except Exception:
        return {"available": False, "model": settings.llm_model, "installed": False}


def explain_for_ui(result: DiagnosisResult) -> dict:
    """Build the structured explanation required by diagnosis 1.2."""
    settings = get_settings()
    fallback = {
        "provider": "template",
        "model": "deterministic-ko-v1",
        "status": "fallback" if not settings.llm_enabled else "unavailable",
        "overview": _overview(result),
        "actionPlan": _action_plan(result),
    }
    if not settings.llm_enabled:
        return fallback

    status = ollama_status()
    if not status["available"] or not status["installed"]:
        return fallback
    try:
        generated = _ask_ollama_json(
            build_prompt(result),
            base_url=settings.ollama_url,
            model=settings.llm_model,
            timeout=settings.llm_timeout,
        )
        return {
            "provider": "ollama",
            "model": settings.llm_model,
            "status": "generated",
            "overview": generated["overview"],
            "actionPlan": generated["actionPlan"],
        }
    except Exception:
        return fallback


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
        "지금 상태, 근거, 다음 조치 순서로 씁니다.",
    ]
    return "\n".join(lines)


def render_template(result: DiagnosisResult) -> str:
    action = _ACTION_LABEL[result.decision.action]
    if not result.findings:
        return "종합 판정: {0}\n{1}\n확보한 항목: {2}".format(
            action,
            result.decision.reason,
            ", ".join(result.coverage) or "없음",
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


def _overview(result: DiagnosisResult) -> str:
    if not result.findings:
        return result.decision.reason
    primary = result.findings[0]
    return "{0} 항목이 가장 우선입니다. {1}".format(primary.title, primary.summary)


def _action_plan(result: DiagnosisResult) -> list[str]:
    actions: list[str] = []
    for finding in result.findings:
        if finding.action_detail and finding.action_detail not in actions:
            actions.append(finding.action_detail)
        if len(actions) == 3:
            break
    return actions or ["현재 설정을 유지하고 다음 정기 진단에서 상태 변화를 확인하세요."]


def _safe_local_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Ollama endpoint must be loopback-only")
    return raw.rstrip("/")


def _request_ollama(body: dict, base_url: str, timeout: float) -> str:
    request = urllib.request.Request(
        _safe_local_url(base_url) + "/api/generate",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    text = (payload.get("response") or "").strip()
    if not text:
        raise RuntimeError("LLM이 빈 응답을 반환했습니다")
    return text


def _ask_ollama(prompt: str, base_url: str, model: str, timeout: float) -> str:
    return _request_ollama(
        {
            "model": model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3},
        },
        base_url,
        timeout,
    )


def _ask_ollama_json(prompt: str, base_url: str, model: str, timeout: float) -> dict:
    text = _request_ollama(
        {
            "model": model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt + "\nJSON으로만 답하세요: {\"overview\": \"...\", \"actionPlan\": [\"...\"]}",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 350},
        },
        base_url,
        timeout,
    )
    value = json.loads(text)
    overview = str(value.get("overview") or "").strip()
    actions = [str(item).strip() for item in value.get("actionPlan", []) if str(item).strip()]
    if not overview or not actions:
        raise RuntimeError("LLM returned an incomplete diagnosis payload")
    return {"overview": overview, "actionPlan": actions[:3]}
