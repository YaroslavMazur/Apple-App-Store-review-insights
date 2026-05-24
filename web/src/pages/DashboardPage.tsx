import { Download, Loader2, RefreshCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { RatingDistribution } from "../components/charts/RatingDistribution";
import { ReviewMap } from "../components/charts/ReviewMap";
import { SentimentBreakdown } from "../components/charts/SentimentBreakdown";
import { InsightsList } from "../components/InsightsList";
import { MetricsSummary } from "../components/MetricsSummary";
import { ReviewTable } from "../components/ReviewTable";
import { SelectedReviewCard } from "../components/SelectedReviewCard";
import { TopKeywords } from "../components/TopKeywords";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { useCollectStream } from "../hooks/useCollectStream";
import { useInsights, useMetrics, useReviews } from "../hooks/useReviewData";
import { rememberApp } from "../lib/recentApps";
import { formatServerDate } from "../lib/dates";
import { StageList } from "../components/StageList";

export function DashboardPage() {
  const { appId: appIdParam } = useParams();
  const [params] = useSearchParams();
  const appId = Number(appIdParam);
  const country = (params.get("country") ?? "us").toLowerCase();

  const metrics = useMetrics(appId, country);
  const insights = useInsights(appId, country);
  const reviews = useReviews(appId, country);
  const collect = useCollectStream();
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedReviewId(null);
  }, [appId, country]);

  const selectedDetails = useMemo(() => {
    if (!selectedReviewId || !reviews.data || !insights.data) return null;
    const review = reviews.data.reviews.find((r) => r.id === selectedReviewId);
    if (!review) return null;
    const point = insights.data.insights.review_map.find(
      (p) => p.review_id === selectedReviewId,
    );
    const sentiment = point?.sentiment ?? null;
    const theme =
      point?.topic_id != null
        ? insights.data.insights.themes.find((t) => t.id === point.topic_id) ?? null
        : null;
    return { review, sentiment, theme };
  }, [selectedReviewId, reviews.data, insights.data]);

  const error = (metrics.error ?? insights.error ?? reviews.error) as
    | { code?: string; status?: number; message?: string }
    | null;

  const notCollected = error?.code === "app_not_found";

  const triggerCollect = async () => {
    const result = await collect.start({ app_id: appId, country, limit: 100 });
    if (result) rememberApp(appId, country);
  };

  if (notCollected) {
    return (
      <div className="container py-10">
        <Card className="mx-auto max-w-xl">
          <CardHeader>
            <CardTitle>No data for this app yet</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              We haven&apos;t collected reviews for app{" "}
              <span className="font-mono">{appId}</span> ({country.toUpperCase()})
              yet. Run a collection now to populate the dashboard.
            </p>
            <div className="flex gap-2">
              <Button onClick={triggerCollect} disabled={collect.isPending}>
                {collect.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    Collecting…
                  </>
                ) : (
                  "Collect now"
                )}
              </Button>
              <Button variant="outline" asChild>
                <Link to="/">Search a different app</Link>
              </Button>
            </div>
            {(collect.isPending || collect.data) && (
              <div className="rounded-lg border bg-muted/40 p-4">
                <StageList stages={collect.stages} />
              </div>
            )}
            {collect.error && (
              <p
                className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                role="alert"
              >
                {collect.error.message}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  const isLoading =
    metrics.isLoading || insights.isLoading || reviews.isLoading;

  return (
    <div className="container space-y-6 py-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            App{" "}
            <span className="font-mono text-base text-muted-foreground">
              {appId}
            </span>{" "}
            <span className="text-sm uppercase text-muted-foreground">
              ({country})
            </span>
          </h1>
          {metrics.data && (
            <p className="mt-1 text-sm text-muted-foreground">
              Last collected {formatServerDate(metrics.data.last_collected_at)}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={triggerCollect}
            disabled={collect.isPending}
          >
            {collect.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <RefreshCcw className="h-4 w-4" aria-hidden />
            )}
            Re-collect
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href={api.csvUrl(appId, country)} download>
              <Download className="h-4 w-4" aria-hidden />
              Download CSV
            </a>
          </Button>
        </div>
      </div>

      {collect.isPending && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Re-collecting…</CardTitle>
          </CardHeader>
          <CardContent>
            <StageList stages={collect.stages} />
          </CardContent>
        </Card>
      )}

      {isLoading && !collect.isPending && <DashboardSkeleton />}

      {!isLoading && metrics.data && insights.data && (
        <>
          <MetricsSummary
            metrics={metrics.data.metrics}
            sentiment={insights.data.insights.sentiment_breakdown}
            lastCollectedAt={metrics.data.last_collected_at}
          />

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Rating distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <RatingDistribution metrics={metrics.data.metrics} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Sentiment breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <SentimentBreakdown
                  breakdown={insights.data.insights.sentiment_breakdown}
                />
              </CardContent>
            </Card>
          </div>

          {reviews.data && insights.data.insights.review_map.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Review map</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Every dot is one review. Position comes from UMAP — semantically
                  similar reviews land near each other. Colors are BERTopic
                  themes. Themes shaded red in the legend are "pain points"
                  (mostly-negative clusters). <strong>Click any dot to read
                  the full review.</strong>
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <ReviewMap
                  points={insights.data.insights.review_map}
                  themes={insights.data.insights.themes}
                  reviews={reviews.data.reviews}
                  onSelect={setSelectedReviewId}
                  selectedId={selectedReviewId}
                />
                {selectedDetails && (
                  <SelectedReviewCard
                    review={selectedDetails.review}
                    sentiment={selectedDetails.sentiment}
                    theme={selectedDetails.theme}
                    onClose={() => setSelectedReviewId(null)}
                  />
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Top keywords in negative reviews</CardTitle>
            </CardHeader>
            <CardContent>
              <TopKeywords themes={insights.data.insights.themes} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Actionable insights</CardTitle>
            </CardHeader>
            <CardContent>
              <InsightsList insights={insights.data.insights.insights} />
            </CardContent>
          </Card>

          {reviews.data && (
            <Card>
              <CardHeader>
                <CardTitle>All reviews ({reviews.data.reviews.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <ReviewTable reviews={reviews.data.reviews} />
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
