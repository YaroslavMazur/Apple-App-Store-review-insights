import { Check, Loader2 } from "lucide-react";
import { cn } from "../lib/cn";
import type { Stage } from "../hooks/useCollectStream";

interface Props {
  stages: Stage[];
  className?: string;
}

function formatDuration(ms?: number): string | null {
  if (ms == null) return null;
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function StageList({ stages, className }: Props) {
  return (
    <ol
      className={cn("space-y-2 text-sm", className)}
      aria-live="polite"
      aria-label="Collection progress"
    >
      {stages.map((stage) => (
        <li
          key={stage.id}
          className={cn(
            "flex items-start gap-3 transition-colors",
            stage.state === "pending" && "text-muted-foreground/60",
            stage.state === "running" && "text-foreground",
            stage.state === "completed" && "text-muted-foreground",
          )}
        >
          <span
            className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center"
            aria-hidden
          >
            {stage.state === "completed" && (
              <Check className="h-4 w-4 text-emerald-500" />
            )}
            {stage.state === "running" && (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            )}
            {stage.state === "pending" && (
              <span className="h-2 w-2 rounded-full bg-muted-foreground/30" />
            )}
          </span>
          <span className="flex-1">
            <span
              className={cn(
                stage.state === "running" && "font-medium text-foreground",
                stage.state === "completed" && "line-through decoration-muted-foreground/40",
              )}
            >
              {stage.label}
            </span>
            {stage.detail && (
              <span className="ml-1 text-xs text-muted-foreground">— {stage.detail}</span>
            )}
          </span>
          {stage.durationMs != null && (
            <span
              className="shrink-0 font-mono text-xs text-muted-foreground"
              aria-hidden
            >
              {formatDuration(stage.durationMs)}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
