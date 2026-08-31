"""수집 게시글 품질 평가 (GPT-2 perplexity 기반).

NSMC로 파인튜닝한 KoGPT-2 모델로 게시글 제목의 perplexity를 구하고,
이를 0-100 품질 점수로 환산한다. 광고/도배성 글을 걸러내는 용도다.

모델은 용량 문제로 저장소에 포함하지 않는다. 사용하려면
``QUALITY_MODEL_DIR`` 환경변수로 모델 디렉터리를 지정하고
``QUALITY_EVAL_ENABLED=true`` 로 켠다. 모델이 없으면 평가를 건너뛰고
입력을 그대로 돌려주므로 크롤링 자체는 항상 동작한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from app.core.config import get_settings

MODEL_CACHE: Dict[str, object] = {
    "model": None,
    "tokenizer": None,
    "device": None,
}


def get_model_dir() -> Path:
    """모델 디렉터리. 설정이 없으면 저장소 옆의 ``nsmc`` 학습 산출물을 기본값으로 본다."""
    settings = get_settings()
    if settings.quality_model_dir:
        return Path(settings.quality_model_dir)
    return Path(__file__).resolve().parents[3] / "nsmc" / "code" / "nsmc_pretrained" / "model"


def load_evaluator(model_dir: Optional[Path] = None, device: str = "cpu"):
    """모델/토크나이저를 1회만 로드해 캐시한다. 준비되지 않았으면 ``(None, None)``."""
    if model_dir is None:
        model_dir = get_model_dir()

    if MODEL_CACHE["model"] is not None and MODEL_CACHE["device"] == device:
        return MODEL_CACHE["model"], MODEL_CACHE["tokenizer"]

    if not Path(model_dir).is_dir():
        print(f"품질 평가 모델 없음 ({model_dir}) - 평가를 건너뜁니다.")
        return None, None

    # torch/transformers 는 무거우므로 실제로 쓸 때만 임포트한다.
    try:
        from transformers import GPT2LMHeadModel, PreTrainedTokenizerFast
    except ImportError as e:
        print(f"품질 평가 의존성 미설치 ({e}) - 평가를 건너뜁니다.")
        return None, None

    try:
        model = GPT2LMHeadModel.from_pretrained(model_dir)
        tokenizer = PreTrainedTokenizerFast.from_pretrained(model_dir)
        model.to(device)
        model.eval()
    except Exception as e:
        print(f"품질 평가 모델 로드 실패: {e}")
        return None, None

    MODEL_CACHE["model"] = model
    MODEL_CACHE["tokenizer"] = tokenizer
    MODEL_CACHE["device"] = device
    return model, tokenizer


def calculate_perplexity(text: str, model, tokenizer, device: str = "cpu") -> Optional[float]:
    if not text or not text.strip():
        return None

    import torch

    encoding = tokenizer(text, max_length=1024, truncation=True, return_tensors="pt")
    input_ids = encoding["input_ids"].to(device)
    if input_ids.shape[1] == 0:
        return None

    with torch.no_grad():
        outputs = model(input_ids=input_ids, labels=input_ids)
        loss = outputs.loss

    if loss is None or not torch.isfinite(loss):
        return None

    return float(torch.exp(loss))


def score_text(perplexity: Optional[float]) -> Optional[float]:
    """perplexity 가 낮을수록(자연스러운 문장일수록) 높은 점수를 준다."""
    import math

    if perplexity is None or not math.isfinite(perplexity) or perplexity <= 0:
        return None

    quality_score = 100.0 - 20.0 * math.log10(perplexity)
    return float(max(0.0, min(100.0, quality_score)))


def evaluate_posts(posts: List[Dict], device: str = "cpu") -> List[Dict]:
    """게시글 목록에 ``perplexity`` / ``quality_score`` 를 채워 반환한다.

    모델이 준비되지 않았으면 입력을 그대로 돌려준다.
    """
    if not posts:
        return posts

    model, tokenizer = load_evaluator(device=device)
    if model is None or tokenizer is None:
        return posts

    evaluated = []
    for post in posts:
        perplexity = calculate_perplexity(post.get("title", ""), model, tokenizer, device=device)
        quality_score = score_text(perplexity)

        result = post.copy()
        result["perplexity"] = round(perplexity, 2) if perplexity is not None else None
        result["quality_score"] = round(quality_score, 2) if quality_score is not None else None
        evaluated.append(result)

    return evaluated
