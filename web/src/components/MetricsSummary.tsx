import { Star, Users, ThumbsUp, ThumbsDown, Clock } from "lucide-react";
import type { Metrics, SentimentBreakdown } from "../api/types";
import { formatServerDate, relativeAgo } from "../lib/dates";
import { Card, CardContent } from "./ui/card";

interface Props {
  metrics: Metrics;
  sentiment: SentimentBreakdown;
  lastCollectedAt: string;
}

function pctPositive(s: SentimentBreakdown): number {
  if (!s.total) return 0;
  return Math.round(
    ((s.counts.positive + s.counts.very_positive) / s.total) * 100,
  );
}
function pctNegative(s: SentimentBreakdown): number {
  if (!s.total) return 0;
  return Math.round(
    ((s.counts.negative + s.counts.very_negative) / s.total) * 100,
  );
}

interface KpiProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}
function Kpi({ icon, label, value, sub }: KpiProps) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </span>
          <span className="text-muted-foreground" aria-hidden>
            {icon}
          </span>
        </div>
        <div className="mt-2 text-2xl font-semibold">{value}</div>
        {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

export function MetricsSummary({ metrics, sentiment, lastCollectedAt }: Props) {
  const stars = "★".repeat(Math.round(metrics.average_rating))
    + "☆".repeat(5 - Math.round(metrics.average_rating));
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <Kpi
        icon={<Star className="h-4 w-4" />}
        label="Average"
        value={metrics.average_rating.toFixed(2)}
        sub={stars}
      />
      <Kpi
        icon={<Users className="h-4 w-4" />}
        label="Reviews"
        value={metrics.total_reviews.toString()}
      />
      <Kpi
        icon={<ThumbsUp className="h-4 w-4 text-emerald-500" />}
        label="Positive"
        value={`${pctPositive(sentiment)}%`}
        sub={`${sentiment.counts.positive + sentiment.counts.very_positive} reviews`}
      />
      <Kpi
        icon={<ThumbsDown className="h-4 w-4 text-rose-500" />}
        label="Negative"
        value={`${pctNegative(sentiment)}%`}
        sub={`${sentiment.counts.negative + sentiment.counts.very_negative} reviews`}
      />
      <Kpi
        icon={<Clock className="h-4 w-4" />}
        label="Collected"
        value={relativeAgo(lastCollectedAt)}
        sub={formatServerDate(lastCollectedAt)}
      />
    </div>
  );
}
