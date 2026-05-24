import type { Theme } from "../api/types";

interface Props {
  themes: Theme[];
}

export function TopKeywords({ themes }: Props) {
  const all = themes
    .flatMap((t) =>
      t.keywords.map((kw) => ({ kw, share: t.share_of_negatives })),
    )
    .reduce<Record<string, number>>((acc, { kw, share }) => {
      acc[kw] = (acc[kw] ?? 0) + share;
      return acc;
    }, {});
  const sorted = Object.entries(all)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 15);

  if (!sorted.length) {
    return (
      <p className="text-sm text-muted-foreground">
        No clustered keywords yet.
      </p>
    );
  }

  const max = sorted[0][1];
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
      {sorted.map(([kw, weight]) => {
        const ratio = weight / max;
        const fontSize = `${0.75 + ratio * 0.75}rem`;
        const opacity = 0.55 + ratio * 0.45;
        return (
          <span
            key={kw}
            className="font-medium text-foreground transition-colors"
            style={{ fontSize, opacity }}
          >
            {kw}
          </span>
        );
      })}
    </div>
  );
}
