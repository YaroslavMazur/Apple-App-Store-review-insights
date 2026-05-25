# Apple App Store Review Analysis

A FastAPI service and React dashboard that turn a public Apple app id into rating metrics, sentiment breakdown, thematic clusters, and prioritized product insights. The entire NLP pipeline runs on local CPU — no external LLM, no API keys, no per-call cost.

A live demo report against Spotify US is in [`sample_report/report.md`](./sample_report/report.md). Project status, milestones, and changelog live in [`CLAUDE.md`](./CLAUDE.md).

---

## Run locally

The fastest path is Docker Compose, which builds and runs both services together:

```bash
docker compose up --build
# API: http://localhost:8000  (OpenAPI at /docs)
# Web: http://localhost:8080
```

For native development, the API needs Python 3.11 with `uv`, the web needs `pnpm`:

```bash
cd api && uv sync && cp .env.example .env
uv run uvicorn app.main:app --reload          # :8000

cd web && pnpm install && cp .env.example .env
pnpm dev                                       # :5173
```

Open the web URL, enter an app id and country (`324684580` / `us` defaults to Spotify), and watch the live progress stream through each pipeline stage before the dashboard renders.

---

## How the pipeline works

A `/collect` request kicks off a sequence of seven discrete stages, each emitting a progress event over NDJSON so the frontend can show what's happening during the 5–25 second wait.

The first stage hits the Apple App Store via the `appstorescraperpy` library, which takes an app id and country and returns up to two thousand of the most recent reviews with their real Apple-assigned ids, ratings, titles, bodies, authors, and timestamps. The library is synchronous, so the service wraps it in `anyio.to_thread.run_sync` and wraps that in a tenacity retry policy with exponential backoff for transient upstream failures.

Sentiment classification is the next stage and runs each review's combined title-plus-body text through `nlptown/bert-base-multilingual-uncased-sentiment`. This model was chosen empirically rather than by reputation. We benchmarked four candidate models against the user's star rating as a proxy ground truth, on a hundred real Spotify reviews from the US store: nlptown reached 66% exact-match accuracy with the rating and 82% within one level, while the alternatives we tried — `tabularisai/multilingual-sentiment-analysis`, `cardiffnlp/twitter-xlm-roberta-base-sentiment`, and `lxyuan/distilbert-base-multilingual-cased-sentiments-student` — landed between 31% and 75%. The nlptown model emits star labels directly (`1 star` through `5 stars`), which map cleanly onto our five-class `SentimentClass` enum without any lossy projection. Crucially, the model never sees the user's actual star rating during inference. It reads only the text, which means a five-star review whose words sound very negative produces a visible disagreement that the dashboard surfaces as a mismatch badge. That divergence is real signal about sarcastic, mis-rated, or non-English-trained-on reviews that pure-rating analysis would silently drop.

After sentiment, every review is embedded into a 384-dimensional vector with `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. This is a CPU-friendly multilingual model with broad language coverage including Ukrainian, Russian, and Chinese — important because App Store reviews come in whatever language the user writes them. The embedding stage runs once and its output feeds both the visual map and the clustering stage, which avoids the common BERTopic pitfall of having one UMAP for clustering and another for visualization that disagree.

The shared 2D projection comes from a single UMAP pass with cosine metric and a fixed `random_state` for layout stability across reruns. Those same two-dimensional coordinates are then fed into BERTopic via a `BaseDimensionalityReduction` passthrough, meaning HDBSCAN clusters reviews in exactly the 2D space the dashboard renders. A reader looking at the map can trust that two dots sitting near each other really are in the same cluster, and a reader looking at a cluster can trust the map's spatial grouping. Cluster keywords come from a `CountVectorizer` configured with English stopwords and bigrams, run through BERTopic's c-TF-IDF scoring so keywords like "ads" or "shuffle" rise above generic terms like "the" or "and".

Once themes are built, every review is attached to exactly one theme and each theme carries two derived metrics: how many of its reviews are negative, and whether that negative share is at least fifty percent. Themes that pass the threshold become pain points. The final stage filters themes to pain points only, ranks them by severity (high above seventy-five percent negative, medium between sixty and seventy-five, low below), and turns them into `Insight` records with a one-sentence description, supporting review count, and the keywords that defined the theme.

Everything — reviews, the full insights report, and a collections audit row — is persisted to SQLite before the response returns. Subsequent reads against `/metrics`, `/insights`, or `/raw` hit the database directly without re-running the pipeline.

---

## What the 2D map shows

The map is the single most useful artifact the pipeline produces. Each dot is one review, positioned according to where its text falls in 384-dimensional embedding space after projection to two dimensions via UMAP with cosine similarity. The intuition is that reviews whose meaning is similar — same complaint, same praise, same topic — end up near each other regardless of language or exact wording. A user complaining about ads in Spanish lands close to a user complaining about ads in English; both land far from someone praising the music catalog.

Color encodes the theme each dot belongs to, with theme order determined by cluster size so the largest themes get the most distinguishable colors. Themes flagged as pain points appear in their normal cluster color but receive a red "pain point" badge in the on-hover tooltip and selected-review card, drawing the eye to clusters that warrant product investigation. The unclustered dots — reviews HDBSCAN couldn't confidently assign — show in muted gray, but in practice this set is small because we tune HDBSCAN's `min_cluster_size` and `min_samples` aggressively for the typical hundred-review run.

Clicking any dot opens a card below the chart with the full review's title, body, rating, model-predicted sentiment, and theme assignment. This closes the loop between the aggregate view (where are users gathered?) and the qualitative view (what are these specific users actually saying?), which is where the analytical value of a clustering pipeline really lives.

---

## Why these choices

The decision to run NLP locally instead of through a hosted LLM was driven by predictability and operational simplicity. An LLM API would deliver higher accuracy on edge cases — particularly sarcasm and idiomatic short text where nlptown demonstrably stumbles — but it introduces per-call cost, network failure modes, latency variance, API key management, and prompt-injection surface area. For a system designed to scan hundreds of reviews per collect and run unmodified on a take-home reviewer's laptop, the local pipeline's deterministic behavior and zero-credential setup outweighs the accuracy lift. The trade-off is documented honestly: text-only sentiment hits roughly two-thirds exact agreement with star ratings on our benchmark data, and the mismatch badge is the design that surfaces that imprecision to the user rather than hiding it.

SQLite via `aiosqlite` is the storage layer because the project's data shape is small, write-light, and well-served by a single-file database with no operational footprint. Three tables — reviews, insights reports, and collections — sit behind a `ReviewRepository` class that's the only code in the service permitted to touch the database. Routes call services, services call the repository, and the repository hides everything below it. This pays off when SQLite hits its limit, which on Cloud Run is the ephemeral filesystem: when an instance scales to zero, its data is gone. The repository pattern means swapping SQLite for Cloud SQL Postgres is a one-file change with no churn in services or routes. We chose to defer that swap rather than build for it speculatively, because for the demo's request pattern (single user, single browser session, collect-and-read inside one window) ephemeral storage is functionally indistinguishable from durable.

The synchronous `/collect` endpoint runs the entire pipeline in one request and returns the result. For the typical hundred-review collect, this takes between five and twenty-five seconds depending on whether the models are warm. A traditional asynchronous job pattern — return `202 Accepted` immediately with a job id, poll a separate endpoint for status — would scale better but adds substantial complexity (a job table, a worker process or queue, a polling client) that isn't justified at current scale. Instead, the dashboard gets a parallel `/collect/stream` endpoint that runs the same pipeline but emits NDJSON events as each stage starts and finishes. The frontend renders those events as a live progress list with per-stage timings, which gives the user something useful to watch during the wait without changing the underlying execution model.

FastAPI was chosen over Flask or Django because the project benefits heavily from typed request and response models (Pydantic v2 across the board), automatic OpenAPI generation that the web build consumes via `openapi-typescript`, and first-class async support for the parts of the pipeline that legitimately wait on I/O. The web client's `web/src/api/types.ts` is regenerated from the live `/openapi.json`, so any contract drift between the two services breaks the web typecheck before it can reach production.

---

## API surface

Five endpoints live under `/api/v1`, plus the `/health` and `/ready` probes at the root.

| Endpoint | Purpose |
|---|---|
| `POST /reviews/collect` | Runs the full pipeline and returns the report in one synchronous response. |
| `POST /reviews/collect/stream` | Same pipeline, NDJSON stream with per-stage `started` / `completed` events. |
| `GET /reviews/{app_id}/metrics?country=us` | Rating metrics computed from persisted reviews. |
| `GET /reviews/{app_id}/insights?country=us` | The persisted `InsightsReport` (sentiment, themes, insights, 2D map). |
| `GET /reviews/{app_id}/raw?country=us&format=json\|csv` | Raw reviews. `format=csv` triggers an attachment download. |

All errors return a consistent envelope `{ "error": { "code", "message", "details" } }`, generated by a single FastAPI exception handler over a `DomainError` hierarchy defined in `app/exceptions.py`. The web client parses this shape exactly once in `web/src/api/client.ts` and exposes it as a typed `ApiError` class.

Swagger UI is at `http://localhost:8000/docs`.

---

## Repository layout

```
api/                  FastAPI service
  app/
    main.py           factory, CORS, middleware, lifespan
    api/v1/reviews.py thin handlers for the five endpoints
    services/         fetcher, metrics, insights
    models/           domain types and request/response schemas
    storage/          aiosqlite repository
  Dockerfile          three-stage: build → model warmup → runtime

web/                  React + Vite + TypeScript
  src/
    api/              generated types and typed fetch client
    hooks/            TanStack Query hooks and the NDJSON streaming hook
    pages/            HomePage and DashboardPage
    components/       ui primitives, charts, tables, and the selected-review card
  Dockerfile + nginx.conf

docs/                 design rationale (decisions.md, nlp-analysis.md)
sample_report/        live Spotify run committed for reference
docker-compose.yml
CLAUDE.md             living status document
```
