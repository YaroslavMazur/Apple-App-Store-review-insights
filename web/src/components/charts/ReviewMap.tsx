import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type {
  Review,
  ReviewPoint,
  SentimentClass,
  Theme,
} from "../../api/types";

interface Props {
  points: ReviewPoint[];
  themes: Theme[];
  reviews: Review[];
  onSelect?: (reviewId: string) => void;
  selectedId?: string | null;
}

const TOPIC_COLORS = [
  "hsl(217 91% 60%)",  // blue
  "hsl(142 71% 45%)",  // green
  "hsl(38 92% 50%)",   // amber
  "hsl(271 91% 65%)",  // violet
  "hsl(0 84% 60%)",    // red
  "hsl(190 95% 50%)",  // cyan
  "hsl(310 85% 60%)",  // pink
  "hsl(60 90% 50%)",   // yellow
  "hsl(165 80% 40%)",  // teal
  "hsl(20 90% 55%)",   // orange
];

const UNCLUSTERED_COLOR = "hsl(var(--muted-foreground) / 0.45)";

const SENTIMENT_LABEL: Record<SentimentClass, string> = {
  very_negative: "Very Negative",
  negative: "Negative",
  neutral: "Neutral",
  positive: "Positive",
  very_positive: "Very Positive",
};

interface ChartPoint extends ReviewPoint {
  title: string;
  themeLabel: string | null;
  color: string;
  isPainPoint: boolean;
}

function buildSeries(points: ReviewPoint[], themes: Theme[], reviews: Review[]) {
  const topicById = new Map(themes.map((t) => [t.id, t]));
  const reviewById = new Map(reviews.map((r) => [r.id, r]));
  const sortedTopics = [...themes].sort(
    (a, b) => b.total_reviews - a.total_reviews,
  );
  const colorByTopic = new Map<number, string>();
  sortedTopics.forEach((t, i) =>
    colorByTopic.set(t.id, TOPIC_COLORS[i % TOPIC_COLORS.length]),
  );

  const seriesByTopic = new Map<string, { name: string; data: ChartPoint[]; color: string }>();
  const unclustered: ChartPoint[] = [];

  for (const point of points) {
    const review = reviewById.get(point.review_id);
    const theme = point.topic_id != null ? topicById.get(point.topic_id) ?? null : null;
    const color =
      point.topic_id != null
        ? colorByTopic.get(point.topic_id) ?? UNCLUSTERED_COLOR
        : UNCLUSTERED_COLOR;
    const enriched: ChartPoint = {
      ...point,
      title: review?.title || "(no title)",
      themeLabel: theme?.label ?? null,
      color,
      isPainPoint: theme?.is_pain_point ?? false,
    };
    if (point.topic_id == null || !theme) {
      unclustered.push(enriched);
      continue;
    }
    const key = String(point.topic_id);
    const existing = seriesByTopic.get(key);
    if (existing) existing.data.push(enriched);
    else
      seriesByTopic.set(key, {
        name: theme.label,
        data: [enriched],
        color,
      });
  }

  const series = [...seriesByTopic.values()];
  if (unclustered.length) {
    series.unshift({
      name: "Unclustered",
      data: unclustered,
      color: UNCLUSTERED_COLOR,
    });
  }
  return series;
}

export function ReviewMap({ points, themes, reviews, onSelect, selectedId }: Props) {
  if (!points.length) {
    return (
      <p className="text-sm text-muted-foreground">
        Not enough reviews to build a map. Run a collection with more reviews.
      </p>
    );
  }

  const series = buildSeries(points, themes, reviews);

  return (
    <div className="space-y-3">
      <div
        className="h-80 w-full"
        role="img"
        aria-label="2D semantic map of reviews, clustered by theme"
      >
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 12, right: 24, bottom: 12, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              type="number"
              dataKey="x"
              hide
              domain={["dataMin", "dataMax"]}
            />
            <YAxis
              type="number"
              dataKey="y"
              hide
              domain={["dataMin", "dataMax"]}
            />
            <ZAxis type="number" range={[55, 55]} />
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              contentStyle={{
                background: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: 8,
                fontSize: 12,
                padding: 8,
              }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as ChartPoint;
                return (
                  <div className="space-y-1">
                    <div className="font-medium text-foreground">
                      {p.title}{" "}
                      <span className="font-mono text-xs text-muted-foreground">
                        {p.rating}★
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {SENTIMENT_LABEL[p.sentiment]}
                      {p.themeLabel ? (
                        <>
                          {" · "}
                          <span style={{ color: p.color }}>{p.themeLabel}</span>
                          {p.isPainPoint && (
                            <span className="ml-1 rounded bg-destructive/15 px-1 text-destructive">
                              pain point
                            </span>
                          )}
                        </>
                      ) : (
                        " · no cluster"
                      )}
                    </div>
                    <div className="text-xs italic text-muted-foreground">
                      Click to read the full review →
                    </div>
                  </div>
                );
              }}
            />
            {series.map((s) => (
              <Scatter
                key={s.name}
                name={s.name}
                data={s.data}
                fill={s.color}
                fillOpacity={s.name === "Unclustered" ? 0.5 : 0.85}
                onClick={(e: unknown) => {
                  const datum = e as ChartPoint | undefined;
                  if (datum?.review_id && onSelect) onSelect(datum.review_id);
                }}
                style={{ cursor: onSelect ? "pointer" : "default" }}
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {series.map((s) => (
          <span key={s.name} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: s.color }}
            />
            <span className="text-muted-foreground">
              {s.name} ({s.data.length})
            </span>
          </span>
        ))}
      </div>

      {selectedId && (
        <p className="text-xs text-muted-foreground">
          Showing details for review <span className="font-mono">{selectedId}</span>.
        </p>
      )}
    </div>
  );
}
