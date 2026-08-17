"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { ApiError } from "@/lib/api";
import {
  createProject,
  deleteProject,
  listProjects,
  type Project,
} from "@/lib/projects-api";

type SortKey = "newest" | "oldest" | "name";

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: d.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined,
  });
}

export function LeaguesView() {
  const { loggedIn, ready } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("newest");
  const [sortOpen, setSortOpen] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const openAuth = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("auth", "signin");
    router.push(`${pathname}?${params.toString()}`);
  }, [pathname, router, searchParams]);

  const refresh = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      setProjects(await listProjects());
    } catch (err) {
      setProjects([]);
      setError(err instanceof ApiError ? err.message : "Could not load leagues.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (!loggedIn) {
      setLoading(false);
      setProjects([]);
      return;
    }
    void refresh();
  }, [ready, loggedIn, refresh]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = projects;
    if (q) {
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.description || "").toLowerCase().includes(q),
      );
    }
    const copy = [...list];
    copy.sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name);
      const at = new Date(a.created_at).getTime();
      const bt = new Date(b.created_at).getTime();
      return sort === "oldest" ? at - bt : bt - at;
    });
    return copy;
  }, [projects, query, sort]);

  const sortLabel =
    sort === "name"
      ? "Sort by Name"
      : sort === "oldest"
        ? "Sort by Oldest"
        : "Sort by Newest";

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setFormError("Enter a league name.");
      return;
    }
    setPending(true);
    try {
      const created = await createProject({
        name: trimmed,
        description: description.trim() || null,
      });
      setProjects((prev) => [created, ...prev]);
      setModalOpen(false);
      setName("");
      setDescription("");
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : "Could not create league.",
      );
    } finally {
      setPending(false);
    }
  }

  async function onDelete(project: Project) {
    const ok = window.confirm(
      `Delete “${project.name}”? This cannot be undone.`,
    );
    if (!ok) return;
    setDeletingId(project.id);
    setError(null);
    try {
      await deleteProject(project.id);
      setProjects((prev) => prev.filter((p) => p.id !== project.id));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not delete league.",
      );
    } finally {
      setDeletingId(null);
    }
  }

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (!loggedIn) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
        <h1 className="font-serif text-3xl font-bold">Leagues</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Sign in to create and manage leagues for your briefings.
        </p>
        <button
          type="button"
          onClick={openAuth}
          className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
        >
          Sign in
        </button>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-10 md:px-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <h1 className="font-serif text-3xl font-bold">Leagues</h1>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <button
                type="button"
                onClick={() => setSortOpen((v) => !v)}
                className="inline-flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground hover:border-ring hover:text-foreground"
              >
                <span>{sortLabel}</span>
                <span className="material-symbols-outlined text-[18px]">
                  expand_more
                </span>
              </button>
              {sortOpen && (
                <div className="absolute right-0 z-10 mt-1 min-w-[180px] rounded-lg border border-border bg-card py-1 shadow-lg">
                  {(
                    [
                      ["newest", "Newest"],
                      ["oldest", "Oldest"],
                      ["name", "Name"],
                    ] as const
                  ).map(([key, label]) => (
                    <button
                      key={key}
                      type="button"
                      className={`block w-full px-3 py-2 text-left text-sm hover:bg-muted ${
                        sort === key ? "text-primary" : "text-foreground"
                      }`}
                      onClick={() => {
                        setSort(key);
                        setSortOpen(false);
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={() => {
                setFormError(null);
                setModalOpen(true);
              }}
              className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
            >
              New league
            </button>
          </div>
        </div>

        <div className="mb-6 flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2.5">
          <span className="material-symbols-outlined text-muted-foreground">
            search
          </span>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search leagues..."
            aria-label="Search leagues"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>

        {error && (
          <p className="mb-4 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading leagues…</p>
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-muted/40 px-6 py-16 text-center">
            <p className="font-serif text-xl font-semibold text-foreground">
              {projects.length === 0 ? "No leagues yet" : "No matching leagues"}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              {projects.length === 0
                ? "Create one to organize projects and briefings."
                : "Try a different search."}
            </p>
            {projects.length === 0 && (
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                className="mt-6 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
              >
                New league
              </button>
            )}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {filtered.map((p) => (
              <article
                key={p.id}
                className="group relative flex flex-col rounded-xl border border-border bg-card/80 p-5 text-left transition-colors hover:border-ring"
              >
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-serif text-lg font-semibold text-foreground">
                    {p.name}
                  </h3>
                  <button
                    type="button"
                    aria-label={`Delete ${p.name}`}
                    disabled={deletingId === p.id}
                    onClick={() => void onDelete(p)}
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-muted hover:text-destructive group-hover:opacity-100 focus:opacity-100 disabled:opacity-50"
                  >
                    <span className="material-symbols-outlined text-[18px]">
                      delete
                    </span>
                  </button>
                </div>
                <p className="mt-2 flex-1 text-sm text-muted-foreground">
                  {p.description?.trim() || "No description yet."}
                </p>
                <time
                  dateTime={p.created_at}
                  className="mt-4 font-mono text-xs text-muted-foreground"
                >
                  {formatDate(p.created_at)}
                </time>
              </article>
            ))}
          </div>
        )}
      </div>

      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex cursor-default items-center justify-center bg-[rgba(4,12,8,0.55)] p-6"
          role="dialog"
          aria-modal="true"
          aria-labelledby="league-create-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) setModalOpen(false);
          }}
        >
          <form
            onSubmit={onCreate}
            className="relative w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              aria-label="Close"
              onClick={() => setModalOpen(false)}
              className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <span className="material-symbols-outlined text-[20px]">close</span>
            </button>
            <h2
              id="league-create-title"
              className="pr-8 font-serif text-xl font-semibold"
            >
              New league
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Organize briefings and future project threads under one league.
            </p>
            <label className="mt-5 block text-sm font-medium">
              Name
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring"
                placeholder="e.g. Premier League Watch"
                autoFocus
              />
            </label>
            <label className="mt-4 block text-sm font-medium">
              Description
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="mt-1.5 w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-ring"
                placeholder="Optional notes for this league"
              />
            </label>
            {formError && (
              <p className="mt-3 text-sm text-destructive">{formError}</p>
            )}
            <div className="mt-6 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={pending}
                className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-60"
              >
                {pending ? "Creating…" : "Create"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
