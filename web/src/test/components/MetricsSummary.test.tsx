import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricsSummary } from "../../components/MetricsSummary";
import type { Metrics, SentimentBreakdown } from "../../api/types";

const metrics: Metrics = {
  total_reviews: 100,
  average_rating: 4.25,
  distribution: [
    { rating: 1, count: 10, percentage: 10 },
    { rating: 2, count: 5, percentage: 5 },
    { rating: 3, count: 10, percentage: 10 },
    { rating: 4, count: 25, percentage: 25 },
    { rating: 5, count: 50, percentage: 50 },
  ],
};

const sentiment: SentimentBreakdown = {
  counts: {
    very_negative: 10,
    negative: 10,
    neutral: 20,
    positive: 30,
    very_positive: 30,
  },
  percentages: {
    very_negative: 10,
    negative: 10,
    neutral: 20,
    positive: 30,
    very_positive: 30,
  },
  total: 100,
};

describe("MetricsSummary", () => {
  it("renders the average rating with two decimals", () => {
    render(
      <MetricsSummary
        metrics={metrics}
        sentiment={sentiment}
        lastCollectedAt={new Date().toISOString()}
      />,
    );
    expect(screen.getByText("4.25")).toBeInTheDocument();
  });

  it("computes positive and negative percentages", () => {
    render(
      <MetricsSummary
        metrics={metrics}
        sentiment={sentiment}
        lastCollectedAt={new Date().toISOString()}
      />,
    );
    // positive + very_positive = 60%
    expect(screen.getByText("60%")).toBeInTheDocument();
    // very_negative + negative = 20%
    expect(screen.getByText("20%")).toBeInTheDocument();
  });

  it("shows the total review count", () => {
    render(
      <MetricsSummary
        metrics={metrics}
        sentiment={sentiment}
        lastCollectedAt={new Date().toISOString()}
      />,
    );
    expect(screen.getByText("100")).toBeInTheDocument();
  });
});
