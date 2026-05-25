import * as React from "react";
import type { Review, SentimentClass } from "../api/types";
import { Badge } from "./ui/badge";
import { Select } from "./ui/select";

interface Props {
  reviews: Review[];
  sentimentByReviewId?: Map<string, SentimentClass>;
}

type SortKey = "rating" | "created_at" | "mismatch";

const SENTIMENT_LABEL: Record<SentimentClass, string> = {
  very_negative: "Very Negative",
  negative: "Negative",
  neutral: "Neutral",
  positive: "Positive",
  very_positive: "Very Positive",
};

const SENTIMENT_TO_STAR: Record<SentimentClass, number> = {
  very_negative: 1,
  negative: 2,
  neutral: 3,
  positive: 4,
  very_positive: 5,
};

function sentimentVariant(
  s: SentimentClass,
): "destructive" | "warning" | "secondary" | "success" {
  if (s === "very_negative" || s === "negative") return "destructive";
  if (s === "neutral") return "secondary";
  return "success";
}

function mismatchDelta(rating: number, sentiment: SentimentClass): number {
  return Math.abs(rating - SENTIMENT_TO_STAR[sentiment]);
}

export function ReviewTable({ reviews, sentimentByReviewId }: Props) {
  const [filter, setFilter] = React.useState("");
  const [sortBy, setSortBy] = React.useState<SortKey>("created_at");
  const [page, setPage] = React.useState(0);
  const pageSize = 10;
  const hasSentiment = !!sentimentByReviewId && sentimentByReviewId.size > 0;

  const filtered = React.useMemo(() => {
    const f = filter.toLowerCase().trim();
    const base = f
      ? reviews.filter(
          (r) =>
            r.title.toLowerCase().includes(f) ||
            r.body.toLowerCase().includes(f) ||
            r.author.toLowerCase().includes(f),
        )
      : reviews;
    const sorted = [...base];
    if (sortBy === "rating") {
      sorted.sort((a, b) => b.rating - a.rating);
    } else if (sortBy === "mismatch" && sentimentByReviewId) {
      sorted.sort((a, b) => {
        const sa = sentimentByReviewId.get(a.id);
        const sb = sentimentByReviewId.get(b.id);
        const da = sa ? mismatchDelta(a.rating, sa) : -1;
        const db = sb ? mismatchDelta(b.rating, sb) : -1;
        return db - da;
      });
    } else {
      sorted.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    }
    return sorted;
  }, [reviews, filter, sortBy, sentimentByReviewId]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pages - 1);
  const slice = filtered.slice(
    safePage * pageSize,
    safePage * pageSize + pageSize,
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          aria-label="Filter reviews"
          placeholder="Filter by title, body, or author…"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setPage(0);
          }}
          className="flex h-9 flex-1 min-w-[200px] rounded-md border border-input bg-background px-3 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Select
          aria-label="Sort reviews"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortKey)}
          className="h-9 w-auto py-0"
        >
          <option value="created_at">Newest first</option>
          <option value="rating">Rating high → low</option>
          {hasSentiment && (
            <option value="mismatch">Rating-vs-sentiment mismatch</option>
          )}
        </Select>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2" title="From the App Store — what the reviewer clicked">
                User rating
              </th>
              {hasSentiment && (
                <th className="px-3 py-2" title="From our NLP model — predicted from the review text">
                  Our sentiment
                </th>
              )}
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Body</th>
              <th className="px-3 py-2">Author</th>
              <th className="px-3 py-2">Date</th>
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => {
              const sentiment = sentimentByReviewId?.get(r.id) ?? null;
              const delta = sentiment ? mismatchDelta(r.rating, sentiment) : 0;
              const isMismatch = sentiment && delta >= 2;
              return (
                <tr key={r.id} className="border-t last:border-b-0">
                  <td className="px-3 py-2 align-top font-semibold">
                    {r.rating}★
                  </td>
                  {hasSentiment && (
                    <td className="px-3 py-2 align-top">
                      {sentiment ? (
                        <div className="flex flex-col items-start gap-1">
                          <Badge variant={sentimentVariant(sentiment)}>
                            {SENTIMENT_LABEL[sentiment]}
                          </Badge>
                          {isMismatch && (
                            <Badge
                              variant="warning"
                              className="text-[10px]"
                              title={`Star rating (${r.rating}★) and predicted sentiment differ by ${delta} levels`}
                            >
                              mismatch
                            </Badge>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  )}
                  <td className="px-3 py-2 align-top font-medium">{r.title}</td>
                  <td className="px-3 py-2 align-top text-muted-foreground">
                    <span className="line-clamp-3 block max-w-md">{r.body}</span>
                  </td>
                  <td className="px-3 py-2 align-top text-xs">{r.author}</td>
                  <td className="px-3 py-2 align-top text-xs text-muted-foreground">
                    {new Date(r.created_at).toLocaleDateString()}
                  </td>
                </tr>
              );
            })}
            {slice.length === 0 && (
              <tr>
                <td
                  colSpan={hasSentiment ? 6 : 5}
                  className="px-3 py-6 text-center text-sm text-muted-foreground"
                >
                  No reviews match the filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {filtered.length} review{filtered.length === 1 ? "" : "s"}
        </span>
        <span className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage(Math.max(0, safePage - 1))}
            disabled={safePage === 0}
            className="rounded-md border px-2 py-1 disabled:opacity-50"
          >
            Prev
          </button>
          <span>
            {safePage + 1} / {pages}
          </span>
          <button
            type="button"
            onClick={() => setPage(Math.min(pages - 1, safePage + 1))}
            disabled={safePage >= pages - 1}
            className="rounded-md border px-2 py-1 disabled:opacity-50"
          >
            Next
          </button>
        </span>
      </div>
    </div>
  );
}
