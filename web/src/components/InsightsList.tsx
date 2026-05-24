import { AlertTriangle, AlertCircle, Info } from "lucide-react";
import type { Insight } from "../api/types";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

interface Props {
  insights: Insight[];
}

function severityBadge(severity: Insight["severity"]) {
  if (severity === "high")
    return (
      <Badge variant="destructive" className="gap-1">
        <AlertTriangle className="h-3 w-3" aria-hidden />
        High
      </Badge>
    );
  if (severity === "medium")
    return (
      <Badge variant="warning" className="gap-1">
        <AlertCircle className="h-3 w-3" aria-hidden />
        Medium
      </Badge>
    );
  return (
    <Badge variant="secondary" className="gap-1">
      <Info className="h-3 w-3" aria-hidden />
      Low
    </Badge>
  );
}

export function InsightsList({ insights }: Props) {
  if (!insights.length) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          No actionable insights — either too few negative reviews to cluster,
          or BERTopic could not identify distinct themes in this set.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {insights.map((insight, i) => (
        <Card key={`${insight.theme_id ?? i}-${insight.title}`}>
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-3">
              <CardTitle className="text-base">{insight.title}</CardTitle>
              {severityBadge(insight.severity)}
            </div>
            <CardDescription>
              {insight.evidence_count} supporting{" "}
              {insight.evidence_count === 1 ? "review" : "reviews"}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0 text-sm">{insight.suggestion}</CardContent>
        </Card>
      ))}
    </div>
  );
}
