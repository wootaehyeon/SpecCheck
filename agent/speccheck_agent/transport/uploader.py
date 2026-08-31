"""스냅샷 업로드.

로컬 우선 원칙: 업로드는 기본값이 아니라 사용자가 명시적으로 요청했을 때만
수행한다 (``scan --upload``). 외부 의존성 없이 표준 urllib만 사용한다.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

ENDPOINT = "/api/scan/snapshots"


class UploadError(RuntimeError):
    """업로드 실패."""


def upload_snapshot(snapshot: dict[str, Any], backend_url: str, timeout: float = 10.0) -> dict[str, Any]:
    url = backend_url.rstrip("/") + ENDPOINT
    body = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise UploadError("{0} {1} - {2}".format(exc.code, exc.reason, detail)) from exc
    except urllib.error.URLError as exc:
        raise UploadError("Backend 연결 실패 ({0}): {1}".format(url, exc.reason)) from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"raw": payload}
