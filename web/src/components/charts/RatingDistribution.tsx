import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Metrics } from "../../api/types";

interface Props {
  metrics: Metrics;
}

export function RatingDistribution({ metrics }: Props) {
  const data = metrics.distribution.map((b) => ({
    rating: `${b.rating}★`,
    count: b.count,
    percentage: b.percentage,
  }));

  return (
    <div className="h-64" role="img" aria-label="Rating distribution bar chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
          <XAxis
            dataKey="rating"
            className="text-xs"
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            allowDecimals={false}
            className="text-xs"
            tickLine={false}
            axisLine={false}
            width={32}
          />
          <Tooltip
            cursor={{ fill: "hsl(var(--muted))" }}
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value, _name, item) => {
              const pct = (item?.payload?.percentage as number | undefined) ?? 0;
              return [`${value} (${pct.toFixed(1)}%)`, "count"];
            }}
          />
          <Bar dataKey="count" fill="hsl(var(--chart-1))" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
