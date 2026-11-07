"""Conservative security findings; process presence alone is not malware evidence."""
from app.diagnosis.engine import Rule, register
from app.schemas.diagnosis import ActionType, Axis, Evidence, Finding, Severity
from app.schemas.telemetry import TelemetrySnapshot


@register
class ProcessTampering(Rule):
    rule_id = "SEC-SYSMON-025"
    title = "Sysmon 프로세스 변조 이벤트 확인 필요"
    requires = ("security",)

    def applicable(self, snapshot):
        return snapshot.scan_mode == "actual" and super().applicable(snapshot)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        events = [e for e in snapshot.data("security").get("events", []) if e.get("event_id") == 25]
        if not events:
            return None
        return Finding(
            rule_id=self.rule_id, title=self.title, axis=Axis.SECURITY,
            severity=Severity.HIGH,
            summary="Sysmon이 프로세스 이미지 변조 이벤트를 기록했습니다. 악성코드 여부는 추가 확인이 필요합니다.",
            recommended_action=ActionType.FIX,
            action_detail="Windows 보안 검사를 실행하고 이벤트 시각의 프로그램과 설치 출처를 확인하세요. 자동 종료·삭제는 수행하지 않습니다.",
            confidence=0.8,
            evidence=[Evidence(source="security.events", detail="Sysmon Event ID 25 기록",
                               value={"count": len(events), "samples": events[:5]})],
        )


@register
class CollectionGap(Rule):
    rule_id = "SEC-SYSMON-COVERAGE"
    title = "보안 관측 범위 제한"
    requires = ("security",)

    def evaluate(self, snapshot: TelemetrySnapshot) -> Finding | None:
        data = snapshot.data("security")
        limited = data.get("log_gap") or data.get("truncated") or any(
            e.get("event_id") == 255 for e in data.get("events", [])
        )
        if not limited:
            return None
        return Finding(
            rule_id=self.rule_id, title=self.title, axis=Axis.SECURITY,
            severity=Severity.INFO,
            summary="로그 유실 가능성, 미처리 이벤트 또는 Sysmon 수집 오류가 있어 전체 기간의 보안 상태를 판단할 수 없습니다.",
            recommended_action=ActionType.KEEP,
            action_detail="미처리 이벤트 수집을 기다리고 Sysmon 로그 보관 용량과 수집 상태를 확인하세요.",
            confidence=1.0,
            evidence=[Evidence(source="security", detail="보안 관측 상태",
                               value={"log_gap": data.get("log_gap"), "truncated": data.get("truncated")})],
        )
