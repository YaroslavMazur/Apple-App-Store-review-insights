// Hand-rolled types mirroring the FastAPI schemas under api/app/models.
// `pnpm gen:api` regenerates a stricter version from /openapi.json into generated.ts.

export type SentimentClass =
  | "very_negative"
  | "negative"
  | "neutral"
  | "positive"
  | "very_positive";

export interface RatingBucket {
  rating: 1 | 2 | 3 | 4 | 5;
  count: number;
  percentage: number;
}

export interface Metrics {
  total_reviews: number;
  average_rating: number;
  distribution: RatingBucket[];
}

export interface SentimentBreakdown {
  counts: Record<SentimentClass, number>;
  percentages: Record<SentimentClass, number>;
  total: number;
}

export interface Theme {
  id: number;
  label: string;
  keywords: string[];
  review_ids: string[];
  total_reviews: number;
  negative_count: number;
  negative_share: number;
  share_of_negatives: number;
  average_rating: number;
  is_pain_point: boolean;
}

export interface Insight {
  title: string;
  severity: "low" | "medium" | "high";
  evidence_count: number;
  theme_id: number | null;
  suggestion: string;
}

export interface ReviewPoint {
  review_id: string;
  x: number;
  y: number;
  sentiment: SentimentClass;
  rating: number;
  topic_id: number | null;
}

export interface InsightsReport {
  sentiment_breakdown: SentimentBreakdown;
  themes: Theme[];
  insights: Insight[];
  review_map: ReviewPoint[];
}

export interface Review {
  id: string;
  app_id: number;
  country: string;
  title: string;
  body: string;
  rating: number;
  author: string;
  created_at: string;
  is_edited: boolean;
}

export interface CollectRequest {
  app_id: number;
  country: string;
  limit?: number;
}

export interface CollectResponse {
  app_id: number;
  country: string;
  collected_at: string;
  review_count: number;
  metrics: Metrics;
  insights: InsightsReport;
}

export interface MetricsResponse {
  app_id: number;
  country: string;
  last_collected_at: string;
  metrics: Metrics;
}

export interface InsightsResponse {
  app_id: number;
  country: string;
  last_collected_at: string;
  insights: InsightsReport;
}

export interface RawReviewsResponse {
  app_id: number;
  country: string;
  last_collected_at: string;
  reviews: Review[];
}

export interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
