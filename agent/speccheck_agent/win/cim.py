"""WMI/CIM 조회 어댑터 (Phase 1).

pywin32/wmi 패키지 의존을 피하기 위해 PowerShell ``Get-CimInstance`` 를
서브프로세스로 호출하고 JSON으로 받는다. 덕분에 Agent는 표준 라이브러리만으로
동작하며, 설치 프로그램(Phase 6) 배포 크기도 작아진다.

PowerShell 프로세스 기동 비용이 조회당 약 2초다. 조회가 여러 개면 반드시
``query_batch`` 를 써서 한 번의 기동으로 처리한다.
"""

from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

# PowerShell 출력이 한국어 Windows의 기본 코드페이지(949)로 깨지지 않도록 UTF-8 고정.
_PREAMBLE = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$ProgressPreference = 'SilentlyContinue'; "
    "$ErrorActionPreference = 'Stop'; "
)

DEFAULT_TIMEOUT = 30.0
BATCH_TIMEOUT = 60.0


class CimError(RuntimeError):
    """CIM 조회 실패."""


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_elevated() -> bool:
    """관리자 권한으로 실행 중인지.

    SMART(``root/wmi``)와 온도 센서는 관리자 권한이 없으면 "액세스 거부"로
    막힌다. 오류 메시지는 로케일마다 달라 문자열로 판별할 수 없으므로,
    권한 자체를 확인해 사용자에게 조치 가능한 사유를 돌려주는 데 쓴다.
    """
    if not is_windows():
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run_powershell(script: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """PowerShell 스크립트를 실행하고 stdout을 반환한다."""
    if not is_windows():
        raise CimError("Windows 환경에서만 사용할 수 있습니다 (현재: {0})".format(platform.system()))

    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _PREAMBLE + script,
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:  # PowerShell 자체가 없는 경우
        raise CimError("powershell 실행 파일을 찾을 수 없습니다") from exc
    except subprocess.TimeoutExpired as exc:
        raise CimError("PowerShell 조회 시간 초과 ({0}s)".format(timeout)) from exc

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise CimError(stderr or "PowerShell 종료 코드 {0}".format(proc.returncode))

    return proc.stdout.decode("utf-8", errors="replace")


def _build_query(
    class_name: str,
    properties: list[str] | None = None,
    namespace: str = "root/cimv2",
    where: str | None = None,
) -> str:
    script = "Get-CimInstance -Namespace {0} -ClassName {1}".format(namespace, class_name)
    if where:
        script += " -Filter '{0}'".format(where)
    if properties:
        script += " | Select-Object " + ", ".join(properties)
    return script


def _spec_to_script(spec: dict[str, Any]) -> str:
    """배치 항목 하나를 PowerShell 표현식으로 바꾼다.

    ``script`` 를 직접 준 항목은 그대로 쓴다. CIM이 아닌 자료원(이벤트 로그의
    ``Get-WinEvent``, 성능 카운터 샘플링 루프)도 같은 기동 안에서 처리하기
    위한 통로다. 여러 문장이 필요하면 ``;`` 로 잇되 개행은 넣지 않는다 —
    배치 스크립트 전체가 한 줄로 합쳐지기 때문이다.
    """
    raw = spec.get("script")
    if raw:
        if "\n" in raw:
            raise CimError("배치 script에는 개행을 넣을 수 없습니다")
        return raw
    return _build_query(
        spec["class_name"],
        spec.get("properties"),
        spec.get("namespace", "root/cimv2"),
        spec.get("where"),
    )


def _rows(parsed: Any) -> list[dict[str, Any]]:
    """PowerShell은 결과가 1건이면 배열이 아닌 단일 객체를 반환한다."""
    if parsed is None:
        return []
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [row for row in parsed if isinstance(row, dict)]
    return []


def query(
    class_name: str,
    properties: list[str] | None = None,
    namespace: str = "root/cimv2",
    where: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """CIM 클래스 하나를 조회해 dict 리스트로 반환한다.

    Args:
        class_name: 예) ``Win32_Processor``
        properties: 선택할 속성. None이면 전체(느리므로 지양).
        namespace: 기본 ``root/cimv2``. WHEA/Storage는 다른 네임스페이스를 쓴다.
        where: CIM 필터. 예) ``DriveType=3``
    """
    script = _build_query(class_name, properties, namespace, where) + " | ConvertTo-Json -Depth 3 -Compress"
    raw = run_powershell(script, timeout=timeout).strip()
    if not raw:
        return []
    try:
        return _rows(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise CimError("CIM 응답 JSON 파싱 실패: {0}".format(raw[:200])) from exc


def query_one(class_name: str, properties: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
    rows = query(class_name, properties, **kwargs)
    return rows[0] if rows else {}


def query_batch(
    specs: dict[str, dict[str, Any]], timeout: float = BATCH_TIMEOUT
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """여러 CIM 조회를 PowerShell 한 번으로 처리한다.

    Args:
        specs: ``{키: {"class_name":..., "properties":[...], "namespace":..., "where":...}}``
            또는 CIM이 아닌 자료원을 쓸 때 ``{키: {"script": "Get-WinEvent ..."}}``.

    Returns:
        ``(결과, 오류)`` 튜플. 개별 조회가 실패해도 나머지는 정상 반환되며,
        실패한 키만 오류 dict에 담긴다. 네임스페이스가 없는 구버전 Windows에서도
        수집 가능한 항목은 모두 살리기 위한 구조다.
    """
    if not specs:
        return {}, {}

    lines = ["$data = [ordered]@{}", "$errors = [ordered]@{}"]
    for key, spec in specs.items():
        inner = _spec_to_script(spec)
        lines.append(
            "try {{ $data['{0}'] = @({1}) }} catch {{ $errors['{0}'] = $_.Exception.Message }}".format(
                key, inner
            )
        )
    lines.append(
        "[ordered]@{ data = $data; errors = $errors } | ConvertTo-Json -Depth 6 -Compress"
    )

    raw = run_powershell("; ".join(lines), timeout=timeout).strip()
    if not raw:
        raise CimError("CIM 배치 조회가 빈 응답을 반환했습니다")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CimError("CIM 배치 응답 JSON 파싱 실패: {0}".format(raw[:200])) from exc

    data_block = parsed.get("data") or {}
    error_block = parsed.get("errors") or {}
    results = {key: _rows(data_block.get(key)) for key in specs}
    errors = {key: str(value) for key, value in error_block.items() if value}
    return results, errors
