"use client";

import {
  sortStages,
  stageLabel,
  useMatchStatus,
} from "@/components/chat/MatchStatusContext";

function statusIcon(status: string): string {
  if (status === "active") return "progress_activity";
  if (status === "complete") return "check_circle";
  if (status === "error") return "error";
  return "radio_button_unchecked";
}

export function MatchStatusPanel() {
  const { stages, running } = useMatchStatus();
  const ordered = sortStages(stages);

  return (
    <aside className="hidden w-[320px] shrink-0 flex-col border-l border-border bg-card/80 lg:flex">
      <div className="border-b border-border p-4">
        <h2 className="flex items-center gap-2 font-serif text-lg font-semibold">
          <span className="material-symbols-outlined text-primary">timeline</span>
          Match Status
          {running && (
            <span className="ml-auto font-mono text-[11px] uppercase text-primary">
              Live
            </span>
          )}
        </h2>
      </div>
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-4">
        {ordered.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No active analysis — send a message to start the match pipeline.
          </p>
        ) : (
          ordered.map((s) => (
            <div
              key={s.key}
              className="flex items-start gap-3 rounded-lg border border-border/60 bg-background/40 px-3 py-2.5"
            >
              <span
                className={`material-symbols-outlined mt-0.5 text-[18px] ${
                  s.status === "active"
                    ? "animate-spin text-primary"
                    : s.status === "complete"
                      ? "text-primary"
                      : s.status === "error"
                        ? "text-destructive"
                        : "text-muted-foreground"
                }`}
              >
                {statusIcon(s.status)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-xs uppercase tracking-wide text-muted-foreground">
                  {s.iteration != null ? `Iter ${s.iteration}` : "Stage"}
                </p>
                <p className="text-sm font-medium text-foreground">
                  {stageLabel(s.stage)}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
