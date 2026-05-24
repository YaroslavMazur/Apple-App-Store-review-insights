import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InsightsList } from "../../components/InsightsList";
import type { Insight } from "../../api/types";

describe("InsightsList", () => {
  it("renders an empty-state when no insights are present", () => {
    render(<InsightsList insights={[]} />);
    expect(screen.getByText(/no actionable insights/i)).toBeInTheDocument();
  });

  it("renders one card per insight with the severity badge", () => {
    const insights: Insight[] = [
      {
        title: "crash bug freeze",
        severity: "high",
        evidence_count: 12,
        theme_id: 0,
        suggestion: "Investigate complaints around crash bug freeze.",
      },
      {
        title: "ads",
        severity: "medium",
        evidence_count: 5,
        theme_id: 1,
        suggestion: "Investigate complaints around ads.",
      },
    ];
    render(<InsightsList insights={insights} />);
    expect(screen.getByText("crash bug freeze")).toBeInTheDocument();
    expect(screen.getByText("ads")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(screen.getByText(/12 supporting reviews/i)).toBeInTheDocument();
    expect(screen.getByText(/5 supporting reviews/i)).toBeInTheDocument();
  });
});
