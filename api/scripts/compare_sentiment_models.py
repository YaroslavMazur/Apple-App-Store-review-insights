"""
Sentiment model + preprocessing bench.

Runs several HF sentiment models on the same fetched App Store reviews under
several preprocessing variants, then reports per-combo accuracy against the
user's star rating.

Usage:
    cd api && uv run python scripts/compare_sentiment_models.py \
        [APP_ID] [COUNTRY] [--limit N]

Defaults: Spotify US, 100 reviews.

The user's star rating is used as a proxy ground truth. It is *not* absolute
truth — sarcastic / mis-rated reviews will register as model "errors" even
when the model is right. We compare *every* model against the same proxy so
relative differences are meaningful.
"""

from __future__ import annotations

import argparse
import asyncio
import random as _random
import re
import sys
import warnings
from collections import Counter
from collections.abc import Callable
from typing import Any

from app.models.domain import Review, SentimentClass
from app.services.fetcher import fetch_all_reviews
from app.services.insights import _URL_RE, _WHITESPACE_RE, MAX_TEXT_CHARS

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

MODELS_5_CLASS = {
    "nlptown": "nlptown/bert-base-multilingual-uncased-sentiment",
    "tabularisai": "tabularisai/multilingual-sentiment-analysis",
}

MODELS_3_CLASS = {
    "cardiffnlp-twitter": "cardiffnlp/twitter-xlm-roberta-base-sentiment",
    "lxyuan-student": "lxyuan/distilbert-base-multilingual-cased-sentiments-student",
}

RATING_TO_SENTIMENT_5 = {
    1: SentimentClass.VERY_NEGATIVE,
    2: SentimentClass.NEGATIVE,
    3: SentimentClass.NEUTRAL,
    4: SentimentClass.POSITIVE,
    5: SentimentClass.VERY_POSITIVE,
}

SENTIMENT_ORDER = [
    SentimentClass.VERY_NEGATIVE,
    SentimentClass.NEGATIVE,
    SentimentClass.NEUTRAL,
    SentimentClass.POSITIVE,
    SentimentClass.VERY_POSITIVE,
]

LABEL_TO_5_CLASS = {
    "1 star": SentimentClass.VERY_NEGATIVE,
    "2 stars": SentimentClass.NEGATIVE,
    "3 stars": SentimentClass.NEUTRAL,
    "4 stars": SentimentClass.POSITIVE,
    "5 stars": SentimentClass.VERY_POSITIVE,
    "Very Negative": SentimentClass.VERY_NEGATIVE,
    "Negative": SentimentClass.NEGATIVE,
    "Neutral": SentimentClass.NEUTRAL,
    "Positive": SentimentClass.POSITIVE,
    "Very Positive": SentimentClass.VERY_POSITIVE,
}

LABEL_TO_3_CLASS = {
    "negative": "negative",
    "neutral": "neutral",
    "positive": "positive",
    "LABEL_0": "negative",
    "LABEL_1": "neutral",
    "LABEL_2": "positive",
    "NEGATIVE": "negative",
    "NEUTRAL": "neutral",
    "POSITIVE": "positive",
}


def rating_to_3class(r: int) -> str:
    if r <= 2:
        return "negative"
    if r == 3:
        return "neutral"
    return "positive"


def sentiment_to_3class(s: SentimentClass) -> str:
    if s in (SentimentClass.VERY_NEGATIVE, SentimentClass.NEGATIVE):
        return "negative"
    if s == SentimentClass.NEUTRAL:
        return "neutral"
    return "positive"


# Cover most emoji ranges: emoticons, symbols, transport, supplemental, flags.
_EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "\U00002600-\U000026ff"
    "\U00002700-\U000027bf"
    "\U0001f1e6-\U0001f1ff"
    "]+",
    flags=re.UNICODE,
)


def _strip_url_ws(text: str) -> str:
    cleaned = _URL_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def preprocess_default(review: Review) -> str:
    parts = [p for p in (review.title, review.body) if p]
    out = _strip_url_ws(" ".join(parts))
    return out[:MAX_TEXT_CHARS]


def preprocess_no_emoji(review: Review) -> str:
    parts = [p for p in (review.title, review.body) if p]
    out = _EMOJI_RE.sub(" ", " ".join(parts))
    out = _strip_url_ws(out)
    return out[:MAX_TEXT_CHARS]


def preprocess_no_emoji_lower(review: Review) -> str:
    return preprocess_no_emoji(review).lower()


def preprocess_body_only(review: Review) -> str:
    out = _strip_url_ws(review.body or "")
    return out[:MAX_TEXT_CHARS]


PREPROCESSORS: dict[str, Callable[[Review], str]] = {
    "default": preprocess_default,
    "no-emoji": preprocess_no_emoji,
    "no-emoji+lower": preprocess_no_emoji_lower,
    "body-only": preprocess_body_only,
}


def classify(
    model_name: str,
    reviews: list[Review],
    preprocess: Callable[[Review], str],
) -> list[tuple[str, float]]:
    from transformers import pipeline

    pipe: Any = pipeline(
        "sentiment-analysis",
        model=model_name,
        tokenizer=model_name,
        truncation=True,
        max_length=512,
    )
    texts = [preprocess(r) or "(empty)" for r in reviews]
    raw = pipe(texts, batch_size=16)
    out: list[tuple[str, float]] = []
    for prediction in raw:
        label = prediction.get("label") if isinstance(prediction, dict) else None
        score = float(prediction.get("score", 0.0)) if isinstance(prediction, dict) else 0.0
        out.append((label or "", score))
    return out


def evaluate_5class(
    reviews: list[Review],
    predictions: list[tuple[str, float]],
) -> dict[str, Any]:
    exact = within_one = mismatches_2plus = total_abs = 0
    confs: list[float] = []
    unknown = 0
    for review, (label, score) in zip(reviews, predictions, strict=True):
        truth = RATING_TO_SENTIMENT_5[review.rating]
        predicted = LABEL_TO_5_CLASS.get(label)
        if predicted is None:
            unknown += 1
            continue
        delta = abs(SENTIMENT_ORDER.index(predicted) - SENTIMENT_ORDER.index(truth))
        if delta == 0:
            exact += 1
        if delta <= 1:
            within_one += 1
        if delta >= 2:
            mismatches_2plus += 1
        total_abs += delta
        confs.append(score)
    n = len(reviews) - unknown
    return {
        "n": n,
        "exact": exact,
        "within_one": within_one,
        "mismatches_2plus": mismatches_2plus,
        "mean_abs_error": total_abs / n if n else 0,
        "mean_confidence": sum(confs) / n if n else 0,
        "unknown_labels": unknown,
    }


def evaluate_3class(
    reviews: list[Review],
    predictions: list[tuple[str, float]],
) -> dict[str, Any]:
    correct = 0
    confs: list[float] = []
    unknown = 0
    for review, (label, score) in zip(reviews, predictions, strict=True):
        truth = rating_to_3class(review.rating)
        norm = label.lower().strip() if label else ""
        predicted_3 = LABEL_TO_3_CLASS.get(label) or LABEL_TO_3_CLASS.get(norm)
        if predicted_3 is None:
            five = LABEL_TO_5_CLASS.get(label)
            if five is not None:
                predicted_3 = sentiment_to_3class(five)
        if predicted_3 is None:
            unknown += 1
            continue
        if predicted_3 == truth:
            correct += 1
        confs.append(score)
    n = len(reviews) - unknown
    return {
        "n": n,
        "exact": correct,
        "accuracy": correct / n if n else 0,
        "mean_confidence": sum(confs) / n if n else 0,
        "unknown_labels": unknown,
    }


def fmt_5(r: dict[str, Any]) -> str:
    return (
        f"exact={r['exact']:>3}/{r['n']:<3} ({r['exact'] / r['n'] * 100:>4.1f}%)  "
        f"within1={r['within_one']:>3}  "
        f"2+off={r['mismatches_2plus']:>3}  "
        f"MAE={r['mean_abs_error']:.2f}  "
        f"conf={r['mean_confidence']:.2f}"
    )


def fmt_3(r: dict[str, Any]) -> str:
    return (
        f"acc={r['exact']:>3}/{r['n']:<3} ({r['accuracy'] * 100:>4.1f}%)  "
        f"conf={r['mean_confidence']:.2f}"
    )


def print_worst_disagreements(
    reviews: list[Review],
    all_preds: dict[str, list[tuple[str, float]]],
    limit: int = 12,
) -> None:
    print(f"\n=== Worst {limit} cases (any model off by 3+ from star rating) ===")
    rows = []
    for i, review in enumerate(reviews):
        truth_idx = SENTIMENT_ORDER.index(RATING_TO_SENTIMENT_5[review.rating])
        max_delta = 0
        per_model = []
        for short, preds in all_preds.items():
            label, score = preds[i]
            five = LABEL_TO_5_CLASS.get(label)
            if five is None:
                three = LABEL_TO_3_CLASS.get(label) or LABEL_TO_3_CLASS.get(
                    label.lower().strip() if label else ""
                )
                truth_3 = rating_to_3class(review.rating)
                ok = three == truth_3
                per_model.append((short, label, score, None, ok))
                continue
            delta = abs(SENTIMENT_ORDER.index(five) - truth_idx)
            max_delta = max(max_delta, delta)
            per_model.append((short, label, score, delta, delta == 0))
        if max_delta >= 3:
            rows.append((max_delta, review, per_model))
    rows.sort(key=lambda r: r[0], reverse=True)
    for _, review, per_model in rows[:limit]:
        body = (review.body or "").replace("\n", " ")
        if len(body) > 70:
            body = body[:67] + "..."
        print(f"\n  {review.rating}★  «{review.title or '(no title)'}» / {body}")
        for short, label, score, delta, ok in per_model:
            mark = "✓" if ok else "✗"
            d_str = f"off={delta}" if delta is not None else "3-class"
            print(f"    {mark} {short:<22} -> {label:<14} conf={score:.2f}  {d_str}")


async def main(app_id: int, country: str, limit: int) -> int:
    print(f"\n=== Fetching every available review for app {app_id} ({country}) ===")
    all_reviews = await fetch_all_reviews(app_id=app_id, country=country)
    print(f"Got {len(all_reviews)} total reviews available")
    if limit < len(all_reviews):
        reviews = _random.sample(all_reviews, limit)
        print(f"Randomly sampled {len(reviews)} reviews")
    else:
        reviews = all_reviews

    rating_dist = Counter(r.rating for r in reviews)
    print("\nUser star-rating distribution:")
    for star in (1, 2, 3, 4, 5):
        c = rating_dist.get(star, 0)
        print(f"  {star}★  n={c:>3}  {'█' * c}")

    five_class_results: dict[str, dict[str, Any]] = {}
    three_class_results: dict[str, dict[str, Any]] = {}
    all_preds_for_diff: dict[str, list[tuple[str, float]]] = {}

    print("\n=== 5-class models (default preprocessing) ===")
    for short, full in MODELS_5_CLASS.items():
        print(f"\n  ▸ {short} ({full})", flush=True)
        preds = classify(full, reviews, preprocess_default)
        all_preds_for_diff[short] = preds
        five = evaluate_5class(reviews, preds)
        three = evaluate_3class(reviews, preds)
        five_class_results[short] = five
        three_class_results[short] = three
        print(f"    5-class: {fmt_5(five)}")
        print(f"    3-class: {fmt_3(three)}")

    print("\n=== 3-class models (default preprocessing) ===")
    for short, full in MODELS_3_CLASS.items():
        print(f"\n  ▸ {short} ({full})", flush=True)
        preds = classify(full, reviews, preprocess_default)
        all_preds_for_diff[short] = preds
        three = evaluate_3class(reviews, preds)
        three_class_results[short] = three
        print(f"    3-class: {fmt_3(three)}")

    best_5 = max(five_class_results.items(), key=lambda kv: kv[1]["exact"])
    print(f"\n=== Preprocessing variants on best 5-class model: {best_5[0]} ===")
    best_full = MODELS_5_CLASS[best_5[0]]
    for pp_name, pp_fn in PREPROCESSORS.items():
        if pp_name == "default":
            continue
        print(f"\n  ▸ {best_5[0]} + {pp_name}", flush=True)
        preds = classify(best_full, reviews, pp_fn)
        all_preds_for_diff[f"{best_5[0]}/{pp_name}"] = preds
        five = evaluate_5class(reviews, preds)
        three = evaluate_3class(reviews, preds)
        print(f"    5-class: {fmt_5(five)}")
        print(f"    3-class: {fmt_3(three)}")

    print("\n=== Summary (3-class accuracy, ranked) ===")
    ranked = sorted(three_class_results.items(), key=lambda kv: kv[1]["accuracy"], reverse=True)
    for name, r in ranked:
        print(f"  {name:<22}  {fmt_3(r)}")

    print("\n=== Summary (5-class exact, ranked — 5-class models only) ===")
    ranked = sorted(five_class_results.items(), key=lambda kv: kv[1]["exact"], reverse=True)
    for name, r in ranked:
        print(f"  {name:<22}  {fmt_5(r)}")

    print_worst_disagreements(reviews, all_preds_for_diff)

    print("\n=== Done ===")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app_id", nargs="?", type=int, default=324684580)
    parser.add_argument("country", nargs="?", default="us")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.app_id, args.country, args.limit)))
