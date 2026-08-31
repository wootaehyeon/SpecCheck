from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
from transformers import GPT2LMHeadModel, PreTrainedTokenizerFast

MODEL_CACHE = {
    "model": None,
    "tokenizer": None,
    "device": None,
}


def get_model_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "nsmc" / "code" / "nsmc_pretrained" / "model"


def load_evaluator(model_dir: Optional[Path] = None, device: str = "cpu"):
    if model_dir is None:
        model_dir = get_model_dir()

    if MODEL_CACHE["model"] is not None and MODEL_CACHE["device"] == device:
        return MODEL_CACHE["model"], MODEL_CACHE["tokenizer"]

    model = GPT2LMHeadModel.from_pretrained(model_dir)
    tokenizer = PreTrainedTokenizerFast.from_pretrained(model_dir)

    model.to(device)
    model.eval()

    MODEL_CACHE["model"] = model
    MODEL_CACHE["tokenizer"] = tokenizer
    MODEL_CACHE["device"] = device
    return model, tokenizer


def calculate_perplexity(text: str, model: GPT2LMHeadModel, tokenizer: PreTrainedTokenizerFast, device: str = "cpu") -> Optional[float]:
    if not text or not text.strip():
        return None

    encoding = tokenizer(
        text,
        max_length=1024,
        truncation=True,
        return_tensors="pt",
    )

    input_ids = encoding["input_ids"].to(device)
    if input_ids.shape[1] == 0:
        return None

    with torch.no_grad():
        outputs = model(input_ids=input_ids, labels=input_ids)
        loss = outputs.loss

    if loss is None or not torch.isfinite(loss):
        return None

    perplexity = float(torch.exp(loss))
    return perplexity


def score_text(perplexity: Optional[float]) -> Optional[float]:
    if perplexity is None or not np.isfinite(perplexity) or perplexity <= 0:
        return None

    quality_score = 100.0 - 20.0 * np.log10(perplexity)
    return float(max(0.0, min(100.0, quality_score)))


def evaluate_posts(posts: List[Dict], device: str = "cpu") -> List[Dict]:
    model, tokenizer = load_evaluator(device=device)
    evaluated = []

    for post in posts:
        title = post.get("title", "")
        perplexity = calculate_perplexity(title, model, tokenizer, device=device)
        quality_score = score_text(perplexity)

        post_result = post.copy()
        post_result["perplexity"] = round(perplexity, 2) if perplexity is not None else None
        post_result["quality_score"] = round(quality_score, 2) if quality_score is not None else None
        evaluated.append(post_result)

    return evaluated
