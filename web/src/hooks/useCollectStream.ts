import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import type { CollectRequest, CollectResponse } from "../api/types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type StageId =
  | "fetch"
  | "metrics"
  | "sentiment"
  | "embed"
  | "cluster"
  | "map"
  | "persist";

export interface Stage {
  id: StageId;
  label: string;
  state: "pending" | "running" | "completed";
  durationMs?: number;
  detail?: string;
}

interface StageStartEvent {
  type: "stage";
  id: StageId;
  state: "started";
  label: string;
}
interface StageDoneEvent {
  type: "stage";
  id: StageId;
  state: "completed";
  duration_ms: number;
  detail?: string;
}
interface ResultEvent {
  type: "result";
  data: CollectResponse;
}
interface ErrorEvent {
  type: "error";
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

type StreamEvent = StageStartEvent | StageDoneEvent | ResultEvent | ErrorEvent;

const STAGE_ORDER: { id: StageId; label: string }[] = [
  { id: "fetch", label: "Fetching reviews from the App Store" },
  { id: "metrics", label: "Computing rating metrics" },
  { id: "sentiment", label: "Classifying sentiment with multilingual DistilBERT" },
  { id: "embed", label: "Embedding reviews with MiniLM" },
  { id: "cluster", label: "Clustering negative reviews with BERTopic" },
  { id: "map", label: "Building 2D semantic map" },
  { id: "persist", label: "Saving to database" },
];

function initialStages(): Stage[] {
  return STAGE_ORDER.map((s) => ({ ...s, state: "pending" }));
}

export function useCollectStream() {
  const qc = useQueryClient();
  const [stages, setStages] = useState<Stage[]>(initialStages);
  const [data, setData] = useState<CollectResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isPending, setIsPending] = useState(false);

  const reset = useCallback(() => {
    setStages(initialStages());
    setData(null);
    setError(null);
  }, []);

  const handle = useCallback(
    (ev: StreamEvent, captured: { result: CollectResponse | null }) => {
      if (ev.type === "stage" && ev.state === "started") {
        setStages((prev) =>
          prev.map((s) =>
            s.id === ev.id ? { ...s, label: ev.label, state: "running" } : s,
          ),
        );
      } else if (ev.type === "stage" && ev.state === "completed") {
        setStages((prev) =>
          prev.map((s) =>
            s.id === ev.id
              ? {
                  ...s,
                  state: "completed",
                  durationMs: ev.duration_ms,
                  detail: ev.detail,
                }
              : s,
          ),
        );
      } else if (ev.type === "result") {
        captured.result = ev.data;
        setData(ev.data);
      } else if (ev.type === "error") {
        setError(new ApiError(ev.code, ev.message, 500, ev.details));
      }
    },
    [],
  );

  const start = useCallback(
    async (body: CollectRequest): Promise<CollectResponse | null> => {
      reset();
      setIsPending(true);

      const captured: { result: CollectResponse | null } = { result: null };
      try {
        const res = await fetch(`${BASE}/api/v1/reviews/collect/stream`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok || !res.body) {
          setError(new ApiError("network", `HTTP ${res.status}`, res.status));
          setIsPending(false);
          return null;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let nl: number;
          while ((nl = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, nl).trim();
            buf = buf.slice(nl + 1);
            if (!line) continue;
            try {
              handle(JSON.parse(line) as StreamEvent, captured);
            } catch {
              /* skip malformed line */
            }
          }
        }

        if (captured.result) {
          const r = captured.result;
          qc.invalidateQueries({ queryKey: ["metrics", r.app_id, r.country] });
          qc.invalidateQueries({ queryKey: ["insights", r.app_id, r.country] });
          qc.invalidateQueries({ queryKey: ["reviews", r.app_id, r.country] });
        }
        return captured.result;
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err
            : new ApiError("network", String(err), 0),
        );
        return null;
      } finally {
        setIsPending(false);
      }
    },
    [handle, qc, reset],
  );

  return { start, reset, stages, data, error, isPending };
}
