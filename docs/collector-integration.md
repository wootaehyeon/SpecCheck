# Collector → Diagnosis 연동 계약

우태현 파트의 WMI/CIM, WHEA, Storage, Performance collector는 아래 형태의 정규화 snapshot을 Local Agent에 전달합니다. Rule Detection이 구현되기 전에는 `findings`를 빈 배열로 보내도 됩니다.

```http
POST http://127.0.0.1:4318/api/scans
Content-Type: application/json
```

```json
{
  "snapshot": {
    "machine": {
      "name": "DESKTOP-01",
      "os": "Windows 11 Pro 24H2",
      "agentVersion": "0.3.0"
    },
    "riskScore": 0,
    "resources": [
      {
        "key": "cpu_usage",
        "label": "CPU",
        "value": 18,
        "unit": "%",
        "status": "normal",
        "detail": "4.20 GHz"
      }
    ],
    "findings": [],
    "inventory": [
      {
        "kind": "CPU",
        "name": "AMD Ryzen 7 7800X3D",
        "detail": "8 Cores / 16 Threads",
        "status": "normal"
      }
    ],
    "sources": [
      { "name": "wmi", "status": "collected" },
      { "name": "cim", "status": "collected" },
      { "name": "whea", "status": "collected" },
      { "name": "storage", "status": "collected" },
      { "name": "performance", "status": "collected" },
      { "name": "sysmon", "status": "not_in_scope" }
    ]
  }
}
```

## 상태 enum

- Resource / Inventory: `normal | warning | critical | unknown`
- Source: `collected | unavailable | permission_required | not_in_scope`
- Finding severity: `info | low | medium | high | critical`
- Finding category: `hardware | software | security`

## 통합 책임 경계

```text
Windows Collector
  → normalized snapshot
  → Rule Detection (findings + riskScore)
  → POST /api/scans
  → Diagnosis JSON v1.0.0
  → SQLite history
  → Local Gemma explanation
  → Basic Scan UI
```

Local Agent는 전달받은 Finding의 사실을 바꾸지 않습니다. Gemma에는 Risk와 Finding의 요약된 근거만 전달하며, 모델 응답은 사용자 설명과 Action Plan에만 사용합니다.
