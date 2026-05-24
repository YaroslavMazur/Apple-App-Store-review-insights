from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.domain import Review, SentimentClass, Theme
from app.services import insights as svc


def _review(rating: int, idx: int, title: str = "t", body: str = "b") -> Review:
    return Review(
        id=f"r{idx}",
        app_id=1,
        country="us",
        title=title,
        body=body,
        rating=rating,
        author="a",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
        is_edited=False,
    )


# ── preprocess ────────────────────────────────────────────────────────────────


def test_preprocess_strips_urls() -> None:
    text = "Check this out: https://example.com/x and www.test.org now"
    assert "https" not in svc.preprocess(text)
    assert "www" not in svc.preprocess(text)


def test_preprocess_collapses_whitespace() -> None:
    assert svc.preprocess("foo   bar\n\nbaz\t\t qux") == "foo bar baz qux"


def test_preprocess_truncates() -> None:
    long_text = "x" * 1000
    assert len(svc.preprocess(long_text)) == svc.MAX_TEXT_CHARS


def test_preprocess_handles_empty() -> None:
    assert svc.preprocess("") == ""
    assert svc.preprocess("   ") == ""


# ── classify_sentiments ───────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    """Make sure each test starts with fresh model singletons."""
    svc._sentiment_pipeline = None
    svc._embedding_model = None


def test_classify_sentiments_maps_labels() -> None:
    reviews = [_review(1, 0, body="bad"), _review(5, 1, body="great")]
    fake_pipeline = MagicMock(
        return_value=[
            {"label": "Very Negative", "score": 0.9},
            {"label": "Very Positive", "score": 0.95},
        ]
    )
    with patch("app.services.insights._get_sentiment_pipeline", return_value=fake_pipeline):
        result = svc.classify_sentiments(reviews)
    assert result == {"r0": SentimentClass.VERY_NEGATIVE, "r1": SentimentClass.VERY_POSITIVE}


def test_classify_sentiments_maps_nlptown_star_labels() -> None:
    """Default model emits '1 star'..'5 stars'; we map to the SentimentClass enum."""
    reviews = [_review(r, i, body=f"r{r}") for i, r in enumerate([1, 3, 5])]
    fake_pipeline = MagicMock(
        return_value=[
            {"label": "1 star", "score": 0.7},
            {"label": "3 stars", "score": 0.5},
            {"label": "5 stars", "score": 0.9},
        ]
    )
    with patch("app.services.insights._get_sentiment_pipeline", return_value=fake_pipeline):
        result = svc.classify_sentiments(reviews)
    assert result == {
        "r0": SentimentClass.VERY_NEGATIVE,
        "r1": SentimentClass.NEUTRAL,
        "r2": SentimentClass.VERY_POSITIVE,
    }


def test_classify_sentiments_empty_returns_empty() -> None:
    assert svc.classify_sentiments([]) == {}


def test_classify_sentiments_unknown_label_defaults_to_neutral() -> None:
    reviews = [_review(3, 0)]
    fake_pipeline = MagicMock(return_value=[{"label": "Garbage", "score": 0.5}])
    with patch("app.services.insights._get_sentiment_pipeline", return_value=fake_pipeline):
        result = svc.classify_sentiments(reviews)
    assert result == {"r0": SentimentClass.NEUTRAL}


# ── compute_sentiment_breakdown ───────────────────────────────────────────────


def test_breakdown_aggregates_counts_and_percentages() -> None:
    classifications = {
        "a": SentimentClass.VERY_NEGATIVE,
        "b": SentimentClass.NEGATIVE,
        "c": SentimentClass.NEUTRAL,
        "d": SentimentClass.POSITIVE,
        "e": SentimentClass.POSITIVE,
    }
    breakdown = svc.compute_sentiment_breakdown(classifications)
    assert breakdown.total == 5
    assert breakdown.counts[SentimentClass.POSITIVE] == 2
    assert breakdown.percentages[SentimentClass.POSITIVE] == 40.0
    assert breakdown.percentages[SentimentClass.VERY_POSITIVE] == 0.0


def test_breakdown_empty() -> None:
    breakdown = svc.compute_sentiment_breakdown({})
    assert breakdown.total == 0
    assert all(c == 0 for c in breakdown.counts.values())
    assert all(p == 0.0 for p in breakdown.percentages.values())


# ── cluster_negative_reviews ──────────────────────────────────────────────────


def test_cluster_skipped_when_too_few_reviews() -> None:
    reviews = [_review(1, 0), _review(2, 1)]
    classifications = {"r0": SentimentClass.NEGATIVE, "r1": SentimentClass.NEGATIVE}
    themes, review_to_topic = svc.cluster_all_reviews(reviews, classifications, None)
    assert themes == []
    assert review_to_topic == {}


def test_cluster_builds_themes_with_sentiment_breakdown() -> None:
    """All reviews are clustered; each theme reports negative_share and is_pain_point."""
    import numpy as np

    # 6 reviews: r0-r2 negative, r3-r5 positive
    reviews = [_review(1, i, body=f"bug {i}") for i in range(6)]
    classifications = {
        "r0": SentimentClass.VERY_NEGATIVE,
        "r1": SentimentClass.VERY_NEGATIVE,
        "r2": SentimentClass.NEGATIVE,
        "r3": SentimentClass.POSITIVE,
        "r4": SentimentClass.POSITIVE,
        "r5": SentimentClass.VERY_POSITIVE,
    }
    coords_2d = np.array([[float(i), float(i)] for i in range(6)])

    fake_topic_model = MagicMock()
    # Topic 0 = r0..r2 (all negative — pain point)
    # Topic 1 = r3..r5 (all positive — not a pain point)
    fake_topic_model.fit_transform.return_value = ([0, 0, 0, 1, 1, 1], None)
    fake_topic_model.get_topic.side_effect = lambda tid: {
        0: [("crash", 0.5), ("bug", 0.3)],
        1: [("love", 0.5), ("great", 0.4)],
    }.get(tid, [])

    with (
        patch("app.services.insights._get_embedding_model", return_value=MagicMock()),
        patch("bertopic.BERTopic", return_value=fake_topic_model),
    ):
        themes, review_to_topic = svc.cluster_all_reviews(
            reviews, classifications, coords_2d
        )

    assert len(themes) == 2
    by_id = {t.id: t for t in themes}
    assert by_id[0].total_reviews == 3
    assert by_id[0].negative_count == 3
    assert by_id[0].negative_share == 100.0
    assert by_id[0].is_pain_point is True
    assert by_id[1].total_reviews == 3
    assert by_id[1].negative_count == 0
    assert by_id[1].negative_share == 0.0
    assert by_id[1].is_pain_point is False
    # Every review got a topic.
    assert review_to_topic == {
        "r0": 0,
        "r1": 0,
        "r2": 0,
        "r3": 1,
        "r4": 1,
        "r5": 1,
    }


def test_cluster_handles_bertopic_failure_gracefully() -> None:
    import numpy as np

    reviews = [_review(1, i) for i in range(4)]
    classifications = {f"r{i}": SentimentClass.NEGATIVE for i in range(4)}
    coords_2d = np.array([[float(i), float(i)] for i in range(4)])

    fake_topic_model = MagicMock()
    fake_topic_model.fit_transform.side_effect = RuntimeError("HDBSCAN says no")

    with (
        patch("app.services.insights._get_embedding_model", return_value=MagicMock()),
        patch("bertopic.BERTopic", return_value=fake_topic_model),
    ):
        themes, review_to_topic = svc.cluster_all_reviews(
            reviews, classifications, coords_2d
        )
    assert themes == []
    assert review_to_topic == {}


def test_cluster_returns_empty_when_no_coords() -> None:
    reviews = [_review(1, i) for i in range(5)]
    classifications = {f"r{i}": SentimentClass.NEGATIVE for i in range(5)}
    themes, review_to_topic = svc.cluster_all_reviews(
        reviews, classifications, coords_2d=None
    )
    assert themes == []
    assert review_to_topic == {}


# ── derive_actionable_insights ────────────────────────────────────────────────


def _theme(
    id: int,
    share: float,
    keywords: list[str] | None = None,
    avg: float = 1.5,
    total: int | None = None,
    negative_share: float | None = None,
) -> Theme:
    kw = keywords or ["x"]
    total_reviews = total if total is not None else int(share)
    # Default: most of the theme is negative (pain point) so the older tests
    # that only set `share` still produce insights.
    neg_share = negative_share if negative_share is not None else 75.0
    neg_count = round(total_reviews * neg_share / 100)
    return Theme(
        id=id,
        label=", ".join(kw),
        keywords=kw,
        review_ids=[f"r{i}" for i in range(total_reviews)],
        total_reviews=total_reviews,
        negative_count=neg_count,
        negative_share=neg_share,
        share_of_negatives=share,
        average_rating=avg,
        is_pain_point=neg_share >= 50 and total_reviews >= 3,
    )


def test_derive_insights_severity_from_negative_share() -> None:
    themes = [
        _theme(0, share=40.0, keywords=["crash"], total=10, negative_share=80.0),
        _theme(1, share=20.0, keywords=["battery"], total=10, negative_share=65.0),
        _theme(2, share=10.0, keywords=["ads"], total=10, negative_share=50.0),
    ]
    insights = svc.derive_actionable_insights(themes)
    assert insights[0].severity == "high"  # 80% >= 75
    assert insights[1].severity == "medium"  # 65% >= 60
    assert insights[2].severity == "low"  # 50% < 60


def test_derive_insights_excludes_non_pain_points() -> None:
    """Themes whose majority is positive shouldn't appear as actionable insights."""
    themes = [
        _theme(0, share=10.0, keywords=["love"], total=20, negative_share=10.0),
        _theme(1, share=40.0, keywords=["crash"], total=10, negative_share=80.0),
    ]
    insights = svc.derive_actionable_insights(themes)
    assert len(insights) == 1
    assert insights[0].theme_id == 1


def test_derive_insights_caps_at_five() -> None:
    themes = [
        _theme(i, share=float(20 - i), keywords=[f"kw{i}"], total=10, negative_share=80.0)
        for i in range(8)
    ]
    insights = svc.derive_actionable_insights(themes)
    assert len(insights) == 5


def test_derive_insights_includes_keywords_in_suggestion() -> None:
    themes = [
        _theme(0, share=25.0, keywords=["crash", "freeze", "bug"], total=10, negative_share=80.0)
    ]
    insights = svc.derive_actionable_insights(themes)
    assert "crash" in insights[0].suggestion
    assert "freeze" in insights[0].suggestion


# ── compute_insights_report (full pipeline orchestration) ─────────────────────


def test_full_pipeline_wires_components_in_order() -> None:
    reviews = [_review(1, 0), _review(5, 1)]
    fake_classifications = {
        "r0": SentimentClass.VERY_NEGATIVE,
        "r1": SentimentClass.VERY_POSITIVE,
    }
    fake_themes = [
        Theme(
            id=0,
            label="bug",
            keywords=["bug"],
            review_ids=["r0", "r2", "r3"],
            total_reviews=3,
            negative_count=3,
            negative_share=100.0,
            share_of_negatives=100.0,
            average_rating=1.0,
            is_pain_point=True,
        )
    ]

    with (
        patch("app.services.insights.classify_sentiments", return_value=fake_classifications) as cs,
        patch("app.services.insights.embed_all", return_value=None),
        patch("app.services.insights.reduce_to_2d", return_value=None),
        patch(
            "app.services.insights.cluster_all_reviews",
            return_value=(fake_themes, {"r0": 0}),
        ) as cn,
        patch("app.services.insights.build_review_map", return_value=[]) as bm,
    ):
        report = svc.compute_insights_report(reviews)

    cs.assert_called_once()
    cn.assert_called_once()
    bm.assert_called_once()
    assert report.sentiment_breakdown.total == 2
    assert report.sentiment_breakdown.counts[SentimentClass.VERY_NEGATIVE] == 1
    assert report.themes == fake_themes
    assert report.review_map == []
    assert len(report.insights) == 1
    assert report.insights[0].severity == "high"


def test_build_review_map_produces_point_per_review() -> None:
    """Map echoes the 2D coords from the shared UMAP pass; topics come through."""
    reviews = [_review(1, 0), _review(5, 1), _review(3, 2)]
    classifications = {
        "r0": SentimentClass.VERY_NEGATIVE,
        "r1": SentimentClass.VERY_POSITIVE,
        "r2": SentimentClass.NEUTRAL,
    }
    review_to_topic = {"r0": 0}

    import numpy as np

    coords_2d = np.array([[0.5, 0.6], [1.0, 1.1], [-0.2, -0.3]])
    points = svc.build_review_map(reviews, classifications, coords_2d, review_to_topic)

    assert len(points) == 3
    assert points[0].review_id == "r0"
    assert points[0].x == 0.5
    assert points[0].y == 0.6
    assert points[0].topic_id == 0
    assert points[0].sentiment == SentimentClass.VERY_NEGATIVE
    assert points[1].topic_id is None  # positive, not clustered
    assert points[1].sentiment == SentimentClass.VERY_POSITIVE
    assert points[2].rating == 3


def test_build_review_map_returns_empty_when_no_coords() -> None:
    reviews = [_review(5, 0), _review(5, 1), _review(5, 2)]
    classifications: dict[str, SentimentClass] = {}
    points = svc.build_review_map(reviews, classifications, coords_2d=None, review_to_topic={})
    assert points == []
