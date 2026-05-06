import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def generate_report(evaluation: dict, build: dict) -> str:
    """OpenAI로 자연어 리포트 생성. API 키 없으면 Mock 반환."""
    if not OPENAI_API_KEY:
        return _mock_report(evaluation, build)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = _build_prompt(evaluation, build)
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content":
                 "당신은 PC 견적 전문가입니다. 컴퓨터를 잘 모르는 초보자도 이해할 수 있게 쉽고 친근하게 설명해주세요."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.7,
        )
        return res.choices[0].message.content
    except Exception as e:
        return _mock_report(evaluation, build) + f"\n\n⚠️ AI 오류: {e}"


def _build_prompt(evaluation: dict, build: dict) -> str:
    return f"""다음 PC 견적을 분석해주세요:

【견적 구성】
- CPU: {build.get('cpu', '미입력')}
- GPU: {build.get('gpu', '미입력')}
- RAM: {build.get('ram', '미입력')}
- 메인보드: {build.get('motherboard', '미입력')}
- 파워: {build.get('psu', '미입력')}
- 케이스: {build.get('case', '미입력')}
- 사용 목적: {build.get('purpose', '게이밍')}

【분석 결과】
- 종합 점수: {evaluation.get('overall_score', 0)}/100 ({evaluation.get('tier', '?')}등급)
- CPU 점수: {evaluation.get('cpu_score', 0):,} (정규화: {evaluation.get('cpu_norm', 0):.1f}%)
- GPU 점수: {evaluation.get('gpu_score', 0):,} (정규화: {evaluation.get('gpu_norm', 0):.1f}%)
- 병목: {evaluation.get('bottleneck_component', '없음')} ({evaluation.get('bottleneck_percentage', 0):.1f}%)

위 정보를 바탕으로 3~4문단의 한국어 리포트를 작성해주세요:
1. 전반적인 평가 및 장점
2. 병목 현상 설명 (있다면)
3. 사용 목적에 적합한지 여부
4. 개선 제안

초보자도 이해할 수 있는 친근한 말투로 작성해주세요."""


def _mock_report(evaluation: dict, build: dict) -> str:
    score = evaluation.get("overall_score", 50)
    tier = evaluation.get("tier", "B")
    bottleneck = evaluation.get("bottleneck_component", "없음")
    purpose = build.get("purpose", "게이밍")

    grade_comment = {
        "S": "최상급 퍼포먼스를 자랑하는 견적입니다! 🏆",
        "A": "우수한 성능의 견적입니다. 대부분의 작업을 거뜬히 소화합니다. 👍",
        "B": "준수한 성능의 견적입니다. 일반적인 사용에 충분합니다.",
        "C": "기본적인 성능의 견적입니다. 업그레이드를 고려해볼 만합니다.",
        "D": "성능 개선이 필요한 견적입니다. 주요 부품 교체를 권장합니다.",
    }.get(tier, "")

    bottleneck_text = ""
    if bottleneck != "없음":
        bottleneck_text = (
            f"\n\n⚠️ **{bottleneck} 병목 현상 감지**: 현재 {bottleneck}의 성능이 "
            f"상대 부품 대비 부족합니다. {bottleneck} 업그레이드를 고려해 보세요."
        )

    return (
        f"**{tier}등급** ({score}점) — {grade_comment}\n\n"
        f"{purpose} 목적으로 구성된 이 견적은 CPU와 GPU의 조합이 "
        f"{'균형 잡혀 있습니다' if bottleneck == '없음' else '다소 불균형합니다'}."
        f"{bottleneck_text}\n\n"
        "💡 *이 리포트는 Mock 데이터입니다. "
        ".env에 OpenAI API 키를 입력하면 실제 AI 분석을 받으실 수 있습니다.*"
    )
