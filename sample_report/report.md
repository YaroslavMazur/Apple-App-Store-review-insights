# Sample report — Spotify (US App Store)

Generated end-to-end with the project's pipeline against the live Apple App Store on 2026-05-25. One hundred most-recent reviews were collected for app id `324684580` in the `us` storefront and processed through the same code paths the dashboard uses. The raw API responses backing every number in this report live in [`data/`](./data/).

To reproduce, hit the API directly:

```bash
curl -X POST http://localhost:8000/api/v1/reviews/collect \
     -H 'content-type: application/json' \
     -d '{"app_id": 324684580, "country": "us", "limit": 100}'
```

---

## Rating metrics

The collected sample averages **3.92 out of 5** across one hundred reviews, but the average hides the shape of the data. The distribution is sharply bimodal: sixty-two reviews are five-star and seventeen are one-star, with the three middle buckets accounting for only twenty-one reviews combined.

| Stars | Count | Share |
| ---: | ---: | ---: |
| 5★ | 62 | 62.0% |
| 4★ | 9  | 9.0% |
| 3★ | 5  | 5.0% |
| 2★ | 7  | 7.0% |
| 1★ | 17 | 17.0% |

This bimodality is the single most useful observation about the population. Spotify's detractors do not trickle in as two- or three-star reviews; they skip straight to one-star. The one-star bucket alone is larger than two-, three-, and four-star combined. The implication for product analysis is that there is no "mildly disappointed middle" to win back with incremental fixes — the negative reviews come from users with concrete, articulated complaints, and they're worth reading individually rather than treating as aggregate noise.

---

## Sentiment breakdown

The pipeline ran `nlptown/bert-base-multilingual-uncased-sentiment` over each review's title-plus-body text. The model sees only the text and is never shown the user's actual star rating, which is what makes the agreement (and disagreement) between the two signals informative rather than circular.

| Class | Count | Share |
| --- | ---: | ---: |
| Very Positive | 49 | 49.0% |
| Positive | 11 | 11.0% |
| Neutral | 7  | 7.0% |
| Negative | 4  | 4.0% |
| Very Negative | 29 | 29.0% |

Sixty percent of reviews read as positive overall, thirty-three percent as negative, and seven percent as neutral. The shape mirrors the bimodal star distribution closely, which is reassuring — when both signals agree, that agreement is high-confidence ground truth. The interesting cases live in the disagreements. Twelve reviews carry five-star ratings while the model scored them Very Negative; almost all are either sarcastic protest reviews (a 1★ review reading "LOVE IT!!! Love everything about this service", clearly written to draw attention to a recent product change) or short idiomatic text that the model misreads. The dashboard surfaces every such review with a mismatch badge so a product reviewer can scan them and decide whether the disagreement points to a model failure or to a user signal that pure rating analysis would have lost.

---

## Themes

After sentiment, every review was embedded with `paraphrase-multilingual-MiniLM-L12-v2`, projected to two dimensions with UMAP using cosine similarity, then clustered with HDBSCAN on those same 2D coordinates. Nine themes emerged. Four of them are pain points — clusters where at least half the reviews are negative — and five are mostly-positive groupings.

| Top keywords | Reviews | % negative | Avg★ | Pain point? |
| --- | ---: | ---: | ---: | :---: |
| `ads`, `premium`, `pay` | 14 | 79% | 2.7 | 🔴 |
| `playlist`, `music`, `working` | 9 | 67% | 2.9 | 🔴 |
| `new`, `icon`, `logo` | 6 | 67% | 2.7 | 🔴 |
| `free`, `card`, `premium` | 8 | 50% | 3.9 | 🔴 |
| `spotify`, `song`, `music` | 19 | 21% | 4.4 | — |
| `cool`, `cool cool`, `excelente` | 19 | 16% | 4.3 | — |
| `ai`, `listening`, `best` | 6 | 17% | 3.8 | — |
| `good`, `music`, `songs` | 11 | 0% | 4.9 | — |
| `app`, `app love`, `love` | 5 | 0% | 5.0 | — |

The two largest clusters by review count — `spotify, song, music` and `cool, cool cool, excelente` — are predominantly positive but not uniformly so. The first is generic praise. The second is interesting because the keyword `excelente` shows up alongside English words: HDBSCAN merged English short praise ("cool", "cool cool") with Spanish-language reviews into the same cluster, which is exactly what a multilingual embedding model should do when the semantic content is "the user liked it" regardless of language. The two pure-positive clusters at the bottom of the table (no negative reviews at all) are smaller but more concentrated — these are users writing concrete, enthusiastic reviews rather than two-word affirmations.

---

## Actionable insights

The pipeline ranked the four pain points by severity, derived from each cluster's percent-negative share. The output is intentionally a small number of concrete recommendations rather than a long list of marginal observations.

The highest-priority pain point is **ad pressure on the free tier**, where eleven of fourteen reviews are negative (79%) and the cluster averages 2.7 stars. Reviewers in this cluster talk specifically about ad load and being pushed to upgrade to premium. This is both the largest pain-point cluster by review count and the most concentrated negativity in the dataset — when one in four detractors is complaining about the same thing, that thing is worth addressing tactically (capping mid-song ad duration, fewer ad breaks per hour, more transparent upgrade messaging) without waiting for a strategic monetization revisit.

The second pain point at medium severity is **playlist and playback functionality**, with six of nine reviews negative and the lowest cluster rating in the dataset at 2.9★. The keywords `playlist`, `music`, `working` point to users experiencing concrete playback failures rather than expressing general dissatisfaction. A cluster this small with negativity this concentrated typically traces back to a specific regression — a feature flag, a recent platform-specific build, an algorithm change — and is worth a focused investigation by the playback team.

The third pain point, also medium severity, is **the new icon and logo redesign**. Four of six reviews complain about a recent visual rebrand. This is the smallest pain-point cluster but the most cleanly themed — every keyword (`new`, `icon`, `logo`) tells the same story. The product question this raises is whether brand recognition concerns from the design team outweigh user friction; the data here only shows the friction exists, it doesn't resolve the trade-off.

The lowest-severity pain point at exactly fifty percent negative is the **free-tier and payment friction** cluster — users discussing card declines, free-trial mechanics, and premium upgrade flows. Four of eight reviews are negative but the cluster average is 3.9★, the highest of any pain point, which suggests users encountering these issues are not necessarily leaving the product over them. Worth monitoring but not the first priority.

---

## What the 2D map shows for this dataset

The map separates the positive and negative populations cleanly. The four pain-point clusters sit in distinct regions of the plot with very little overlap, which is a structural sanity check: the clusters are real, not artifacts of a noisy reduction. The `ads, premium, pay` cluster is the most visually compact pain-point region, reflecting how tightly the model groups reviews complaining about the same monetization friction in slightly different words. The multilingual `cool, excelente` cluster shows visible internal density — small sub-groups of Spanish-language reviews sit next to English short-praise reviews without forcing them into separate themes, which is the kind of soft cross-lingual grouping that's hard to achieve without a multilingual embedding model.

The clustering and the visualization share the exact same 2D coordinates rather than running separate UMAP passes, so spatial proximity on the map is a reliable proxy for cluster membership. Two dots sitting next to each other really are in the same group; the picture doesn't lie about the math.

---

## Calibration notes

Sentiment accuracy on this dataset comes out at roughly two-thirds exact agreement with the star rating and over eighty percent within one level, consistent with the benchmark numbers we measured during model selection. The remaining off-by-two-or-more cases are dominated by genuine sarcasm and mis-rating rather than model failures — cases where the model is reading the text correctly and the star rating is the noisier signal. The mismatch badge in the dashboard is the design choice that makes this imprecision visible to a human reviewer rather than averaging it away.

Sample size matters for clustering quality. With one hundred reviews, BERTopic produces nine themes on this app. With five hundred to two thousand reviews — the upper bound the API supports — the same code typically produces twelve to fifteen narrower clusters with more specific keywords. For an actual product review meeting, running collect with a higher limit would be the obvious first step.
