"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  getLiveEvents,
  type LiveEventsResponse,
} from "@/lib/live-events-api";

function score(value: number | null): string {
  return value == null ? "–" : String(value);
}

function syncedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function LiveEventsView() {
  const [data, setData] = useState<LiveEventsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    setError(null);
    try {
      setData(await getLiveEvents());
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load live events.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 60_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return (
    <div className="h-full overflow-y-auto px-6 py-10 md:px-10">
      <div className="mx-auto max-w-4xl">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full bg-primary shadow-[0_0_10px_var(--primary)]"
                aria-hidden="true"
              />
              <p className="font-mono text-xs uppercase tracking-widest text-primary">
                Live feed
              </p>
            </div>
            <h1 className="mt-2 font-serif text-3xl font-bold">Live Events</h1>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              Scores and match states from the configured football MCP provider.
            </p>
          </div>
          <button
            type="button"
            disabled={loading || refreshing}
            onClick={() => void refresh(true)}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium hover:border-ring disabled:opacity-60"
          >
            <span
              className={`material-symbols-outlined text-[18px] ${refreshing ? "animate-spin" : ""}`}
            >
              refresh
            </span>
            Refresh
          </button>
        </header>

        <div className="mt-8" aria-live="polite" aria-busy={loading}>
          {loading ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {[0, 1].map((item) => (
                <div
                  key={item}
                  className="h-44 animate-pulse rounded-2xl border border-border bg-card"
                />
              ))}
            </div>
          ) : error ? (
            <div className="rounded-2xl border border-destructive/40 bg-destructive/10 px-6 py-10 text-center">
              <span className="material-symbols-outlined text-3xl text-destructive">
                signal_disconnected
              </span>
              <p className="mt-2 font-semibold">Live feed unavailable</p>
              <p className="mt-1 text-sm text-muted-foreground">{error}</p>
              <button
                type="button"
                onClick={() => void refresh(true)}
                className="mt-4 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
              >
                Try again
              </button>
            </div>
          ) : data && data.events.length > 0 ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {data.events.map((event) => (
                <article
                  key={event.id}
                  className="rounded-2xl border border-border bg-card p-5 shadow-sm"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="truncate font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
                      {event.competition}
                    </p>
                    <span className="shrink-0 rounded-full bg-primary/15 px-2.5 py-1 font-mono text-[11px] font-semibold uppercase text-primary">
                      {event.minute || event.status}
                    </span>
                  </div>

                  <div className="mt-5 grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-3">
                    <p className="truncate font-semibold">{event.home_team}</p>
                    <p className="font-mono text-2xl font-bold">
                      {score(event.home_score)}
                    </p>
                    <p className="truncate font-semibold">{event.away_team}</p>
                    <p className="font-mono text-2xl font-bold">
                      {score(event.away_score)}
                    </p>
                  </div>

                  <p className="mt-5 border-t border-border pt-3 text-xs text-muted-foreground">
                    {event.status}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-border bg-muted/40 px-6 py-16 text-center">
              <span className="material-symbols-outlined text-4xl text-primary">
                sports_soccer
              </span>
              <p className="mt-3 font-serif text-xl font-semibold">
                No live matches
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                {data?.message || "Check back when the next fixture kicks off."}
              </p>
            </div>
          )}
        </div>

        {data && (
          <footer className="mt-5 flex flex-wrap items-center justify-between gap-2 font-mono text-[11px] text-muted-foreground">
            <span>{data.provider ? `Source: ${data.provider}` : "Provider offline"}</span>
            <span>Updated {syncedAt(data.updated_at)} · auto-refreshes every 60s</span>
          </footer>
        )}
      </div>
    </div>
  );
}
