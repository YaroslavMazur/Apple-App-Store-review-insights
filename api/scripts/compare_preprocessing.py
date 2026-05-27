"""
Focused preprocessing benchmark for nlptown.

Runs nlptown on the same fetched reviews under many preprocessing variants,
to find out whether any text cleanup measurably improves sentiment accuracy
against the user's star rating.

Usage:
    cd api && uv run python scripts/compare_preprocessing.py \
        [APP_ID] [COUNTRY] [--limit N]
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

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

MODEL = "nlptown/bert-base-multilingual-uncased-sentiment"
MAX_CHARS = 500

RATING_TO_SENTIMENT = {
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
LABEL_TO_5 = {
    "1 star": SentimentClass.VERY_NEGATIVE,
    "2 stars": SentimentClass.NEGATIVE,
    "3 stars": SentimentClass.NEUTRAL,
    "4 stars": SentimentClass.POSITIVE,
    "5 stars": SentimentClass.VERY_POSITIVE,
}

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_WS_RE = re.compile(r"\s+")
_EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f\U0001f780-\U0001f7ff\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff\U0001fa00-\U0001fa6f\U0001fa70-\U0001faff"
    "\U00002600-\U000026ff\U00002700-\U000027bf\U0001f1e6-\U0001f1ff"
    "]+",
    flags=re.UNICODE,
)
_PUNCT_RUNS_RE = re.compile(r"([!?.,])\1{2,}")  # !!!  → !
_REPEAT_CHARS_RE = re.compile(r"(.)\1{2,}")  # sooooo → soo
_NON_LETTER_RUN_RE = re.compile(r"[^\w\s.!?,'\"-]+")


def _base(text: str) -> str:
    out = _URL_RE.sub(" ", text)
    out = _WS_RE.sub(" ", out).strip()
    return out[:MAX_CHARS]


def pp_default(r: Review) -> str:
    return _base(" ".join(p for p in (r.title, r.body) if p))


def pp_no_emoji(r: Review) -> str:
    text = " ".join(p for p in (r.title, r.body) if p)
    return _base(_EMOJI_RE.sub(" ", text))


def pp_no_emoji_lower(r: Review) -> str:
    return pp_no_emoji(r).lower()


def pp_title_only(r: Review) -> str:
    return _base(r.title or "")


def pp_body_only(r: Review) -> str:
    return _base(r.body or "")


def pp_no_punct_runs(r: Review) -> str:
    """!!!! → !, sooooo → soo."""
    text = " ".join(p for p in (r.title, r.body) if p)
    text = _PUNCT_RUNS_RE.sub(r"\1", text)
    text = _REPEAT_CHARS_RE.sub(r"\1\1", text)
    return _base(text)


def pp_no_emoji_no_punct_runs(r: Review) -> str:
    text = " ".join(p for p in (r.title, r.body) if p)
    text = _EMOJI_RE.sub(" ", text)
    text = _PUNCT_RUNS_RE.sub(r"\1", text)
    text = _REPEAT_CHARS_RE.sub(r"\1\1", text)
    return _base(text)


def pp_ascii_only(r: Review) -> str:
    """Strip ALL non-ASCII chars (emoji, accented letters, CJK, etc.)."""
    text = " ".join(p for p in (r.title, r.body) if p)
    text = text.encode("ascii", "ignore").decode("ascii")
    return _base(text)


def pp_letters_only(r: Review) -> str:
    """Keep only letters, spaces, and basic punctuation."""
    text = " ".join(p for p in (r.title, r.body) if p)
    text = _NON_LETTER_RUN_RE.sub(" ", text)
    return _base(text)


def pp_first_60(r: Review) -> str:
    """Short truncation — first 60 chars only."""
    return _base(" ".join(p for p in (r.title, r.body) if p))[:60]


def pp_body_then_title(r: Review) -> str:
    """Swap order: body first, then title (some models weight beginning more)."""
    parts = [p for p in (r.body, r.title) if p]
    return _base(" ".join(parts))


VARIANTS: dict[str, Callable[[Review], str]] = {
    "default                  ": pp_default,
    "no-emoji                 ": pp_no_emoji,
    "no-emoji + lowercase     ": pp_no_emoji_lower,
    "title only               ": pp_title_only,
    "body only                ": pp_body_only,
    "no-punct-runs (!!!→!)    ": pp_no_punct_runs,
    "no-emoji + no-punct-runs ": pp_no_emoji_no_punct_runs,
    "ascii only (drop accents)": pp_ascii_only,
    "letters + basic punct    ": pp_letters_only,
    "first 60 chars only      ": pp_first_60,
    "body then title (reorder)": pp_body_then_title,
}


def classify_all(reviews: list[Review]) -> dict[str, list[tuple[SentimentClass, float]]]:
    from transformers import pipeline

    print(f"\n  Loading {MODEL}…", flush=True)
    pipe: Any = pipeline(
        "sentiment-analysis",
        model=MODEL,
        tokenizer=MODEL,
        truncation=True,
        max_length=512,
    )

    out: dict[str, list[tuple[SentimentClass, float]]] = {}
    for name, fn in VARIANTS.items():
        texts = [fn(r) or "(empty)" for r in reviews]
        raw = pipe(texts, batch_size=16)
        preds: list[tuple[SentimentClass, float]] = []
        for pred in raw:
            label = pred.get("label") if isinstance(pred, dict) else None
            score = float(pred.get("score", 0.0)) if isinstance(pred, dict) else 0.0
            preds.append((LABEL_TO_5.get(label, SentimentClass.NEUTRAL), score))
        out[name] = preds
        # Quick eval to print progress
        exact = sum(
            1
            for r, (p, _) in zip(reviews, preds, strict=True)
            if p == RATING_TO_SENTIMENT[r.rating]
        )
        print(f"    {name.strip()}  → exact={exact}/{len(reviews)}", flush=True)
    return out


def evaluate(reviews: list[Review], preds: list[tuple[SentimentClass, float]]) -> dict[str, float]:
    exact = within1 = off2 = total_abs = 0
    confs: list[float] = []
    for r, (p, s) in zip(reviews, preds, strict=True):
        truth_idx = SENTIMENT_ORDER.index(RATING_TO_SENTIMENT[r.rating])
        pred_idx = SENTIMENT_ORDER.index(p)
        delta = abs(pred_idx - truth_idx)
        if delta == 0:
            exact += 1
        if delta <= 1:
            within1 += 1
        if delta >= 2:
            off2 += 1
        total_abs += delta
        confs.append(s)
    n = len(reviews)
    return {
        "exact": exact,
        "within1": within1,
        "off2": off2,
        "mae": total_abs / n,
        "conf": sum(confs) / n,
    }


def print_change_table(
    reviews: list[Review],
    base_preds: list[tuple[SentimentClass, float]],
    variant_preds: dict[str, list[tuple[SentimentClass, float]]],
) -> None:
    print("\n=== Per-review changes vs default (only rows where any variant differs) ===")
    rows = []
    for i, review in enumerate(reviews):
        base_pred = base_preds[i][0]
        differs = any(variant_preds[v][i][0] != base_pred for v in variant_preds)
        if not differs:
            continue
        rows.append((i, review))

    if not rows:
        print("  No variant changed any prediction.")
        return

    print(f"  {len(rows)} reviews where at least one variant differs from default.\n")
    for i, review in rows[:20]:
        truth = RATING_TO_SENTIMENT[review.rating]
        body = (review.body or "").replace("\n", " ")
        if len(body) > 60:
            body = body[:57] + "..."
        print(f"  {review.rating}★→{truth.value:<14} «{review.title or ''}» / {body}")
        for name, preds in variant_preds.items():
            p, s = preds[i]
            mark = "✓" if p == truth else " "
            diff = "" if p == base_preds[i][0] else " ←diff"
            print(f"    {mark} {name} {p.value:<14} conf={s:.2f}{diff}")
        print()


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

    print("\n=== Running nlptown across all preprocessing variants ===")
    all_preds = classify_all(reviews)

    print("\n=== Summary ===")
    print(f"  {'variant':<27} {'exact':<8} {'within1':<9} {'off2+':<7} {'MAE':<6} {'conf':<5}")
    print("  " + "─" * 65)
    base_name = next(iter(VARIANTS))
    base_metrics = evaluate(reviews, all_preds[base_name])
    for name, preds in all_preds.items():
        m = evaluate(reviews, preds)
        d_exact = m["exact"] - base_metrics["exact"]
        marker = ""
        if name == base_name:
            marker = "← baseline"
        elif d_exact > 0:
            marker = f"+{d_exact}"
        elif d_exact < 0:
            marker = f"{d_exact}"
        print(
            f"  {name} "
            f"{m['exact']:>3}/100  "
            f"{m['within1']:>3}/100   "
            f"{m['off2']:>3}/100  "
            f"{m['mae']:>4.2f}  "
            f"{m['conf']:>.2f}   {marker}"
        )

    print_change_table(reviews, all_preds[base_name], all_preds)

    print("\n=== Done ===")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("app_id", nargs="?", type=int, default=324684580)
    parser.add_argument("country", nargs="?", default="us")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.app_id, args.country, args.limit)))
