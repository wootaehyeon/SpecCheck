"""Agent-owned diagnosis, compatibility and shopping workflow using backend tools.

Uses only the standard library. Provider credentials remain on the backend;
external shopping links contain product queries, never device credentials.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlencode, urlsplit

from .watch import NoRedirect, validate_connection

LABELS = {"keep": "현재 유지", "fix": "설정·소프트웨어 조치", "purchase": "부품 교체 검토"}
SHOP_HOSTS = {"www.ebay.com", "www.ebay.co.uk", "www.ebay.de", "www.ebay.com.au",
              "www.ebay.ca", "ebay.com", "ebay.co.uk", "ebay.de", "ebay.com.au", "ebay.ca",
              "search.shopping.naver.com", "search.danawa.com"}


def eligible_candidate(candidate: dict) -> bool:
    return (candidate.get("compatibilityStatus") in ("passed", "conditional")
            and not any(check.get("status") == "failed" for check in candidate.get("checks", [])))


class AssistanceError(ValueError):
    """A bounded error safe to display without response bodies or tokens."""


def safe_shop_url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return (url.scheme == "https" and url.hostname in SHOP_HOSTS
                and not url.username and not url.password and url.port in (None, 443)
                and not any(c in value for c in "\r\n\t"))
    except (TypeError, ValueError):
        return False


def _get(connection: dict, path: str, *, private=False) -> dict:
    headers = {"Accept": "application/json"}
    if private:
        headers["Authorization"] = "Bearer " + connection["writer_token"]
    request = urllib.request.Request(connection["backend_url"] + path, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=25) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise AssistanceError("추천 응답이 너무 큽니다. 서버 상태를 확인해주세요.")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("response must be an object")
        return result
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            message = "연결 권한이 만료되었거나 변경됐습니다. 웹에서 새 코드로 연결해주세요."
        elif exc.code == 404:
            message = "진단 자료가 없거나 서버 업데이트가 필요합니다. 수집 후 다시 확인해주세요."
        else:
            message = "추천 서버가 응답하지 못했습니다. 잠시 후 다시 시도해주세요."
        raise AssistanceError(message) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        if isinstance(exc, AssistanceError):
            raise
        raise AssistanceError("추천 정보를 확인하지 못했습니다. 서버 주소와 연결 상태를 확인해주세요.") from None


def run_assistance(connection: dict, *, snapshot_id: str | None = None, fetch_quotes=True) -> dict:
    """Orchestrate own diagnosis, eligible parts and quotes; never place orders."""
    connection = validate_connection(dict(connection))
    query = "?" + urlencode({"snapshot_id": snapshot_id}) if snapshot_id else ""
    context = _get(connection, "/api/monitor/assistance" + query, private=True)
    if context.get("device_id") != connection["device_id"] or (
        snapshot_id is not None and context.get("snapshot_id") != snapshot_id
    ):
        raise AssistanceError("현재 PC의 진단과 응답이 일치하지 않습니다. 다시 연결해주세요.")
    decision = context.get("decision")
    if context.get("unavailable") or not isinstance(decision, dict) or decision.get("action") not in LABELS:
        raise AssistanceError("진단을 완료하지 못해 추천을 보류합니다. 다음 수집 후 다시 확인해주세요.")
    recommendations = context.get("recommendations", []) if decision["action"] == "purchase" else []
    if not isinstance(recommendations, list):
        raise AssistanceError("추천 형식을 확인하지 못했습니다. 서버를 확인해주세요.")
    context["recommendations"] = recommendations
    parts = {}
    for recommendation in recommendations:
        for candidate in recommendation.get("candidates", []):
            if not eligible_candidate(candidate):
                continue
            for part in candidate.get("parts", []):
                if isinstance(part.get("key"), str):
                    parts[part["key"]] = part
    market = {"offers": [], "products": []}
    market_message = "가격·재고 미확인. 추천 창의 ‘추천·가격 새로고침’으로 조회하세요."
    if fetch_quotes and parts:
        try:
            market = _get(connection, "/api/purchase/quotes?" + urlencode(
                [("product_id", key) for key in sorted(parts)[:32]]))
            if (not isinstance(market.get("offers"), list) or not isinstance(market.get("products"), list)
                    or not all(isinstance(item, dict) for item in market["offers"] + market["products"])):
                raise AssistanceError("판매 정보 형식을 확인하지 못했습니다.")
            market_message = "조회된 판매 정보만 표시합니다. 통화별 비교이며 관세·부가세는 제외됩니다."
        except AssistanceError:
            market = {"offers": [], "products": []}
            market_message = "가격 조회에 실패했습니다. 기술적 추천은 유지하며 판매처에서 가격을 확인하세요."
    return build_report(context, market, market_message)


def build_report(context: dict, market: dict, market_message: str) -> dict:
    action = context["decision"]["action"]
    lines = ["판단: " + LABELS[action], context["decision"].get("reason", ""),
             "기준 스캔: " + str(context.get("snapshot_id", "")), ""]
    if isinstance(context.get("received_at"), (int, float)):
        lines.insert(3, "서버 수신: " + datetime.fromtimestamp(context["received_at"]).astimezone().isoformat(timespec="seconds"))
    links = []
    for finding in context.get("findings", []):
        lines.extend(["[진단] " + str(finding.get("title") or ""),
                      str(finding.get("summary") or ""), str(finding.get("action_detail") or ""), ""])
    eligible = set()
    for recommendation in context.get("recommendations", []):
        lines.append("[교체 제안] " + str(recommendation.get("title", "")))
        for candidate in recommendation.get("candidates", []):
            if not eligible_candidate(candidate):
                lines.append("호환 조건을 확인하지 못한 후보는 구매 연결에서 제외했습니다.")
                continue
            lines.extend([("권장 후보: " if candidate.get("recommended") else "비교 후보: ") + candidate.get("title", ""),
                          candidate.get("summary", "")])
            for check in candidate.get("checks", []):
                lines.append(("추가 확인: " if check.get("status") != "passed" else "확인 조건: ")
                             + check.get("label", "") + " / " + check.get("detail", ""))
            for part in candidate.get("parts", []):
                eligible.add(part.get("key"))
                name = part.get("name", "")
                lines.append("제품: " + name + " / " + ", ".join(part.get("specifications", [])))
                query = part.get("searchQuery") or name
                for merchant, base, parameter in [
                    ("eBay", "https://www.ebay.com/sch/i.html", "_nkw"),
                    ("네이버쇼핑", "https://search.shopping.naver.com/search/all", "query"),
                    ("다나와", "https://search.danawa.com/dsearch.php", "query"),
                ]:
                    links.append({"label": name + " / " + merchant + " 검색",
                                  "url": base + "?" + urlencode({parameter: query})})
        lines.append("")
    if action == "purchase" and not context.get("recommendations"):
        lines.extend(["검증 가능한 제품 후보를 만들지 못했습니다. 확인되지 않은 모델을 추천하지 않습니다.", ""])
    if eligible:
        lines.extend(["[판매 정보]", market_message])
        for status in market.get("products", []):
            if status.get("product_id") in eligible:
                lines.append(status.get("message", "가격 미확인"))
        for offer in market.get("offers", []):
            if (offer.get("product_id") not in eligible or not safe_shop_url(offer.get("url", ""))
                    or offer.get("availability") == "out_of_stock"):
                continue
            currency = offer.get("currency", "")
            lines.append("{0}: 상품 {1} {2} / 한국 배송 {3} / 합계 {4} / 조회 {5}".format(
                offer.get("title", ""), currency, offer.get("amount", "미확인"),
                str(offer["shipping"]) if offer.get("shipping") is not None else "미확인",
                str(offer["total"]) if offer.get("total") is not None else "미확인", offer.get("observed_at", "미확인")))
            lines.append("재고: " + ("있음·API 추정" if offer.get("availability") == "in_stock" else "미확인"))
            links.append({"label": str(offer.get("title", "")) + " / 판매 상품", "url": offer["url"]})
        lines.extend(["", "호환 검사는 확인 가능한 조건에 한합니다. 실제 장착 조건과 판매처의 최종 가격·배송·보증을 확인하세요.",
                      "결제는 선택한 판매처에서 직접 진행합니다. 공개 구매이력은 사용자 직접 기록이며 결제 미검증 자료입니다."])
    return {"device_id": context["device_id"], "snapshot_id": context["snapshot_id"], "action": action,
            "text": "\n".join(lines), "links": links}
