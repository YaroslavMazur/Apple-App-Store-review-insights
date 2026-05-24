import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { SentimentBreakdown as SB, SentimentClass } from "../../api/types";

const LABELS: Record<SentimentClass, string> = {
  very_negative: "Very Negative",
  negative: "Negative",
  neutral: "Neutral",
  positive: "Positive",
  very_positive: "Very Positive",
};

const COLORS: Record<SentimentClass, string> = {
  very_negative: "hsl(var(--chart-5))",
  negative: "hsl(var(--chart-3))",
  neutral: "hsl(var(--muted-foreground))",
  positive: "hsl(var(--chart-2))",
  very_positive: "hsl(var(--chart-1))",
};

const ORDER: SentimentClass[] = [
  "very_negative",
  "negative",
  "neutral",
  "positive",
  "very_positive",
];

interface Props {
  breakdown: SB;
}

export function SentimentBreakdown({ breakdown }: Props) {
  const data = ORDER.map((cls) => ({
    name: LABELS[cls],
    cls,
    value: breakdown.counts[cls],
    percentage: breakdown.percentages[cls],
  })).filter((d) => d.value > 0);

  return (
    <div className="h-64" role="img" aria-label="Sentiment breakdown donut chart">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={2}
          >
            {data.map((entry) => (
              <Cell key={entry.cls} fill={COLORS[entry.cls]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value, _name, item) => {
              const payload = item?.payload as
                | { name: string; percentage: number }
                | undefined;
              const pct = payload?.percentage ?? 0;
              return [`${value} (${pct.toFixed(1)}%)`, payload?.name ?? ""];
            }}
          />
          <Legend
            verticalAlign="bottom"
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
