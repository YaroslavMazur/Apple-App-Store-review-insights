"""
NLP insights pipeline: sentiment classification, theme clustering, actionable
insights, 2D semantic map.

ML imports are deferred inside loader functions so app startup and unit tests
don't pay the transformers/torch import cost.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from threading import Lock
from typing import Any, Literal

from app.config import get_settings
from app.logging import get_logger
from app.models.domain import (
    NEGATIVE_CLASSES,
    Insight,
    InsightsReport,
    Review,
    ReviewPoint,
    SentimentBreakdown,
    SentimentClass,
    Theme,
)

logger = get_logger("insights")

# MiniLM truncates at 128 tokens (~600 chars); DistilBERT caps near 512.
MAX_TEXT_CHARS = 500

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_WHITESPACE_RE = re.compile(r"\s+")

# nlptown emits "1 star".."5 stars"; tabularisai emits "Very Negative".."Very Positive".
_LABEL_TO_CLASS: dict[str, SentimentClass] = {
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


def preprocess(text: str) -> str:
    if not text:
        return ""
    cleaned = _URL_RE.sub(" ", text)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned[:MAX_TEXT_CHARS]


def _combine(review: Review) -> str:
    parts = [p for p in (review.title, review.body) if p]
    return preprocess(" ".join(parts))


_sentiment_lock = Lock()
_embedding_lock = Lock()
_sentiment_pipeline: Any = None
_embedding_model: Any = None


def _get_sentiment_pipeline() -> Any:
    global _sentiment_pipeline
    if _sentiment_pipeline is None:
        with _sentiment_lock:
            if _sentiment_pipeline is None:
                from transformers import pipeline

                settings = get_settings()
                logger.info("insights.load_sentiment", model=settings.sentiment_model)
                _sentiment_pipeline = pipeline(  # type: ignore[call-overload]
                    "sentiment-analysis",
                    model=settings.sentiment_model,
                    tokenizer=settings.sentiment_model,
                    truncation=True,
                )
    return _sentiment_pipeline


def _get_embedding_model() -> Any:
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer

                settings = get_settings()
                logger.info("insights.load_embeddings", model=settings.embedding_model)
                _embedding_model = SentenceTransformer(settings.embedding_model)
    return _embedding_model


def classify_sentiments(reviews: Sequence[Review]) -> dict[str, SentimentClass]:
    if not reviews:
        return {}
    texts = [_combine(r) for r in reviews]
    pipe = _get_sentiment_pipeline()
    raw = pipe(texts, batch_size=16)
    out: dict[str, SentimentClass] = {}
    for review, prediction in zip(reviews, raw, strict=True):
        label = prediction.get("label") if isinstance(prediction, dict) else None
        if label not in _LABEL_TO_CLASS:
            logger.warning("insights.unknown_label", label=label, review_id=review.id)
            out[review.id] = SentimentClass.NEUTRAL
        else:
            out[review.id] = _LABEL_TO_CLASS[label]
    logger.info("insights.sentiment_classified", count=len(out))
    return out


def compute_sentiment_breakdown(
    classifications: dict[str, SentimentClass],
) -> SentimentBreakdown:
    counts: dict[SentimentClass, int] = {cls: 0 for cls in SentimentClass}
    for cls in classifications.values():
        counts[cls] += 1
    total = sum(counts.values())
    percentages = {cls: (round(n / total * 100, 2) if total else 0.0) for cls, n in counts.items()}
    return SentimentBreakdown(counts=counts, percentages=percentages, total=total)


def reduce_to_2d(embeddings: Any) -> Any | None:
    """
    Single UMAP pass shared by clustering and visualization, so a point's
    cluster id and its on-chart position come from the same reduction.
    """
    if embeddings is None or len(embeddings) < 3:
        return None
    import umap

    n_neighbors = min(15, len(embeddings) - 1)
    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=max(2, n_neighbors),
        min_dist=0.05,
        metric="cosine",
        random_state=42,
    )
    try:
        return reducer.fit_transform(embeddings)
    except Exception as exc:
        logger.warning("insights.umap_2d_failed", error=str(exc), count=len(embeddings))
        return None


PAIN_POINT_NEGATIVE_SHARE = 50.0


def cluster_all_reviews(
    reviews: Sequence[Review],
    classifications: dict[str, SentimentClass],
    coords_2d: Any | None = None,
) -> tuple[list[Theme], dict[str, int]]:
    """Cluster every review into themes. Returns (themes, review_id -> topic_id)."""
    if len(reviews) < 3 or coords_2d is None:
        logger.info(
            "insights.cluster_skipped",
            reason="too_few_reviews" if len(reviews) < 3 else "no_coords",
            count=len(reviews),
        )
        return [], {}

    texts = [_combine(r) for r in reviews]
    n = len(reviews)

    from bertopic import BERTopic
    from bertopic.dimensionality import BaseDimensionalityReduction
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer

    # Passthrough so BERTopic uses our already-reduced 2D coords instead of running UMAP again.
    passthrough = BaseDimensionalityReduction()

    # Scale with dataset size: 100 reviews -> 5, 1000 -> 20.
    min_cluster_size = max(3, min(25, n // 20))
    hdbscan_model = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=1,
        cluster_selection_method="leaf",
        metric="euclidean",
        prediction_data=True,
    )

    vectorizer = CountVectorizer(stop_words="english", min_df=1, ngram_range=(1, 2))
    topic_model = BERTopic(
        embedding_model=_get_embedding_model(),
        umap_model=passthrough,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer,
        calculate_probabilities=False,
        verbose=False,
    )
    try:
        topics, _ = topic_model.fit_transform(texts, coords_2d)
    except Exception as exc:
        logger.warning("insights.bertopic_failed", error=str(exc), count=n)
        return [], {}

    # Reassign HDBSCAN outliers to their nearest cluster so the map is fully colored.
    if -1 in topics:
        try:
            topics = topic_model.reduce_outliers(texts, topics, strategy="embeddings")
        except Exception as exc:
            logger.warning("insights.reduce_outliers_failed", error=str(exc))

    review_to_topic: dict[str, int] = {}
    members: dict[int, list[Review]] = {}
    for review, topic_id in zip(reviews, topics, strict=True):
        if topic_id == -1:
            continue
        members.setdefault(int(topic_id), []).append(review)
        review_to_topic[review.id] = int(topic_id)

    if not members:
        return [], {}

    total_negatives = sum(1 for r in reviews if classifications.get(r.id) in NEGATIVE_CLASSES)

    themes: list[Theme] = []
    for topic_id, members_in_topic in members.items():
        keywords = _extract_keywords(topic_model, topic_id)
        label = _format_label(keywords)
        neg_count = sum(
            1 for r in members_in_topic if classifications.get(r.id) in NEGATIVE_CLASSES
        )
        size = len(members_in_topic)
        neg_share = round(neg_count / size * 100, 2) if size else 0.0
        share_of_negatives = round(neg_count / total_negatives * 100, 2) if total_negatives else 0.0
        avg_rating = sum(r.rating for r in members_in_topic) / size
        themes.append(
            Theme(
                id=topic_id,
                label=label,
                keywords=keywords,
                review_ids=[r.id for r in members_in_topic],
                total_reviews=size,
                negative_count=neg_count,
                negative_share=neg_share,
                share_of_negatives=share_of_negatives,
                average_rating=round(avg_rating, 2),
                is_pain_point=neg_share >= PAIN_POINT_NEGATIVE_SHARE and size >= 3,
            )
        )
    themes.sort(key=lambda t: t.total_reviews, reverse=True)
    logger.info(
        "insights.clusters_built",
        n_themes=len(themes),
        n_reviews=n,
        n_pain_points=sum(1 for t in themes if t.is_pain_point),
    )
    return themes, review_to_topic


def _extract_keywords(topic_model: Any, topic_id: int, top_n: int = 5) -> list[str]:
    raw = topic_model.get_topic(topic_id) or []
    return [str(word) for word, _score in raw[:top_n] if word]


def _format_label(keywords: list[str]) -> str:
    if not keywords:
        return "Uncategorized"
    return ", ".join(keywords[:3])


def derive_actionable_insights(themes: Sequence[Theme]) -> list[Insight]:
    """Pick up to 5 pain-point themes (>=50% negative, >=3 negative reviews)."""
    pain_points = [t for t in themes if t.is_pain_point and t.negative_count >= 3]
    ranked = sorted(pain_points, key=lambda t: t.negative_count, reverse=True)[:5]
    insights: list[Insight] = []
    for theme in ranked:
        severity: Literal["low", "medium", "high"]
        if theme.negative_share >= 75:
            severity = "high"
        elif theme.negative_share >= 60:
            severity = "medium"
        else:
            severity = "low"
        kw_phrase = ", ".join(theme.keywords[:3]) or theme.label
        suggestion = (
            f"Investigate complaints around {kw_phrase} — "
            f"{theme.negative_count}/{theme.total_reviews} reviews in this theme are negative "
            f"({theme.negative_share:.0f}%), avg rating {theme.average_rating:.1f} stars."
        )
        insights.append(
            Insight(
                title=theme.label,
                severity=severity,
                evidence_count=theme.negative_count,
                theme_id=theme.id,
                suggestion=suggestion,
            )
        )
    return insights


def embed_all(reviews: Sequence[Review]) -> Any | None:
    """Embed every review once. Returned matrix is reused by clustering and the 2D map."""
    if len(reviews) < 3:
        return None
    embedding_model = _get_embedding_model()
    texts = [_combine(r) for r in reviews]
    return embedding_model.encode(texts, batch_size=32, show_progress_bar=False)


def build_review_map(
    reviews: Sequence[Review],
    classifications: dict[str, SentimentClass],
    coords_2d: Any | None,
    review_to_topic: dict[str, int],
) -> list[ReviewPoint]:
    if coords_2d is None or len(reviews) < 3:
        return []

    return [
        ReviewPoint(
            review_id=r.id,
            x=float(coords_2d[i][0]),
            y=float(coords_2d[i][1]),
            sentiment=classifications.get(r.id, SentimentClass.NEUTRAL),
            rating=r.rating,
            topic_id=review_to_topic.get(r.id),
        )
        for i, r in enumerate(reviews)
    ]


def compute_insights_report(reviews: Iterable[Review]) -> InsightsReport:
    """End-to-end pipeline: sentiment -> cluster -> actionable insights -> 2D map."""
    reviews_list = list(reviews)
    classifications = classify_sentiments(reviews_list)
    breakdown = compute_sentiment_breakdown(classifications)

    embeddings = embed_all(reviews_list)
    coords_2d = reduce_to_2d(embeddings)
    themes, review_to_topic = cluster_all_reviews(reviews_list, classifications, coords_2d)
    review_map = build_review_map(reviews_list, classifications, coords_2d, review_to_topic)
    insights = derive_actionable_insights(themes)
    return InsightsReport(
        sentiment_breakdown=breakdown,
        themes=themes,
        insights=insights,
        review_map=review_map,
    )
