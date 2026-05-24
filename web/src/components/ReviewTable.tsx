import * as React from "react";
import type { Review } from "../api/types";

interface Props {
  reviews: Review[];
}

type SortKey = "rating" | "created_at";

export function ReviewTable({ reviews }: Props) {
  const [filter, setFilter] = React.useState("");
  const [sortBy, setSortBy] = React.useState<SortKey>("created_at");
  const [page, setPage] = React.useState(0);
  const pageSize = 10;

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
    } else {
      sorted.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      );
    }
    return sorted;
  }, [reviews, filter, sortBy]);

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
        <select
          aria-label="Sort reviews"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortKey)}
          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
        >
          <option value="created_at">Newest first</option>
          <option value="rating">Rating high → low</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-3 py-2">Rating</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Body</th>
              <th className="px-3 py-2">Author</th>
              <th className="px-3 py-2">Date</th>
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => (
              <tr key={r.id} className="border-t last:border-b-0">
                <td className="px-3 py-2 align-top font-semibold">
                  {r.rating}★
                </td>
                <td className="px-3 py-2 align-top font-medium">{r.title}</td>
                <td className="px-3 py-2 align-top text-muted-foreground">
                  <span className="line-clamp-3 block max-w-md">{r.body}</span>
                </td>
                <td className="px-3 py-2 align-top text-xs">{r.author}</td>
                <td className="px-3 py-2 align-top text-xs text-muted-foreground">
                  {new Date(r.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
            {slice.length === 0 && (
              <tr>
                <td
                  colSpan={5}
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
