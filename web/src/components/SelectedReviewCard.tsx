import { X } from "lucide-react";
import type { Review, SentimentClass, Theme } from "../api/types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";

interface Props {
  review: Review;
  sentiment: SentimentClass | null;
  theme: Theme | null;
  onClose: () => void;
}

const SENTIMENT_LABEL: Record<SentimentClass, string> = {
  very_negative: "Very Negative",
  negative: "Negative",
  neutral: "Neutral",
  positive: "Positive",
  very_positive: "Very Positive",
};

function sentimentVariant(
  s: SentimentClass | null,
): "destructive" | "warning" | "secondary" | "success" {
  if (s === "very_negative" || s === "negative") return "destructive";
  if (s === "neutral") return "secondary";
  if (s === "very_positive" || s === "positive") return "success";
  return "secondary";
}

export function SelectedReviewCard({ review, sentiment, theme, onClose }: Props) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0 pb-3">
        <div className="space-y-1">
          <CardTitle className="text-base">{review.title || "(no title)"}</CardTitle>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono font-semibold text-foreground">
              {review.rating}★
            </span>
            {sentiment && (
              <Badge variant={sentimentVariant(sentiment)}>
                {SENTIMENT_LABEL[sentiment]}
              </Badge>
            )}
            {theme && (
              <Badge variant="outline">
                Theme: {theme.label}
                {theme.is_pain_point && (
                  <span className="ml-1 text-destructive">· pain point</span>
                )}
              </Badge>
            )}
            <span className="text-muted-foreground">
              by {review.author} · {new Date(review.created_at).toLocaleDateString()}
              {review.is_edited && " (edited)"}
            </span>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Close review details"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="pt-0 text-sm leading-relaxed text-foreground/90">
        {review.body || (
          <span className="italic text-muted-foreground">(no body)</span>
        )}
      </CardContent>
    </Card>
  );
}
