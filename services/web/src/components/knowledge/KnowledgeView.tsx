"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import {
  ApiError,
  fetchKnowledgeStats,
  listKnowledgeFiles,
  uploadKnowledgeFile,
  type KnowledgeFile,
  type KnowledgeStats,
} from "@/lib/knowledge-api";

const ACCEPT =
  ".pdf,.txt,.md,.csv,.xlsx,image/*,application/pdf,text/plain,text/markdown,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function formatNumber(n: number): string {
  return n.toLocaleString();
}

function statusLabel(status: string): string {
  if (status === "ingested") return "Ready";
  if (status === "processing") return "Indexing…";
  if (status === "pending") return "Queued";
  if (status === "failed") return "Failed";
  return status;
}

export function KnowledgeView() {
  const { loggedIn, ready } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const inputRef = useRef<HTMLInputElement>(null);

  const [stats, setStats] = useState<KnowledgeStats>({
    chunks: 0,
    files: 0,
    memory_tokens: 0,
  });
  const [files, setFiles] = useState<KnowledgeFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openAuth = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("auth", "signup");
    router.push(`${pathname}?${params.toString()}`);
  }, [pathname, router, searchParams]);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [nextStats, nextFiles] = await Promise.all([
        fetchKnowledgeStats(),
        listKnowledgeFiles(),
      ]);
      setStats(nextStats);
      setFiles(nextFiles);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load Ball Knowledge.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (!loggedIn) {
      setLoading(false);
      return;
    }
    void refresh();
  }, [ready, loggedIn, refresh]);

  // Poll while ingest is in flight
  useEffect(() => {
    if (!loggedIn) return;
    const busy = files.some(
      (f) => f.status === "pending" || f.status === "processing",
    );
    if (!busy) return;
    const t = window.setInterval(() => {
      void refresh();
    }, 2500);
    return () => window.clearInterval(t);
  }, [files, loggedIn, refresh]);

  async function uploadMany(list: FileList | File[]) {
    const arr = Array.from(list);
    if (!arr.length) return;
    setUploading(true);
    setError(null);
    try {
      for (const file of arr) {
        await uploadKnowledgeFile(file);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
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
        <h1 className="font-serif text-3xl font-bold">Ball Knowledge</h1>
        <p className="max-w-md text-sm text-muted-foreground">
          Sign up to upload match reports and build your personal RAG corpus.
        </p>
        <button
          type="button"
          onClick={openAuth}
          className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground"
        >
          Sign up
        </button>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-10 md:px-10">
      <div className="mx-auto max-w-3xl">
        <h1 className="font-serif text-3xl font-bold">Ball Knowledge</h1>
        <p className="mt-2 text-muted-foreground">
          Your account RAG corpus — not tied to a league. Drop match reports,
          PDFs, and notes here.
        </p>

        <label
          className={`mt-8 flex min-h-52 cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border border-dashed px-6 text-center transition-colors ${
            dragOver
              ? "border-primary bg-primary/10"
              : "border-border bg-muted hover:border-ring"
          } ${uploading ? "pointer-events-none opacity-70" : ""}`}
          onDragEnter={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setDragOver(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files?.length) {
              void uploadMany(e.dataTransfer.files);
            }
          }}
        >
          <span className="material-symbols-outlined text-4xl text-primary">
            upload_file
          </span>
          <strong className="font-semibold">
            {uploading ? "Uploading…" : "Drag & drop documents here"}
          </strong>
          <p className="text-sm text-muted-foreground">
            PDF, TXT, MD, CSV, XLSX, or images — or click to browse
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="sr-only"
            disabled={uploading}
            onChange={(e) => {
              if (e.target.files?.length) void uploadMany(e.target.files);
            }}
          />
        </label>

        {error && (
          <p className="mt-4 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        <div className="mt-5 grid gap-3 sm:grid-cols-3" aria-label="Knowledge base totals">
          {[
            {
              label: "Chunks",
              value: loading ? "—" : formatNumber(stats.chunks),
              hint: "Indexed for retrieval",
            },
            {
              label: "Files",
              value: loading ? "—" : formatNumber(stats.files),
              hint: stats.files === 0 ? "Upload your first document" : "In your account KB",
            },
            {
              label: "Memory Tokens",
              value: loading ? "—" : formatTokens(stats.memory_tokens),
              hint: "Indexed knowledge budget",
            },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-xl border border-border bg-card p-4"
            >
              <p className="font-mono text-xs uppercase text-muted-foreground">
                {card.label}
              </p>
              <p className="mt-1 text-2xl font-bold">{card.value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{card.hint}</p>
            </div>
          ))}
        </div>

        <div className="mt-8">
          <h2 className="font-serif text-xl font-semibold">Files</h2>
          {loading ? (
            <p className="mt-3 text-sm text-muted-foreground">Loading…</p>
          ) : files.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">
              Upload your first document to build Ball Knowledge.
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-border rounded-xl border border-border bg-card">
              {files.map((f) => (
                <li
                  key={f.id}
                  className="flex items-start justify-between gap-3 px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{f.filename}</p>
                    <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                      {f.chunks_indexed > 0
                        ? `${f.chunks_indexed} chunks · ${formatTokens(f.tokens_indexed)} tokens`
                        : statusLabel(f.status)}
                      {f.error_message ? ` · ${f.error_message}` : ""}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-md px-2 py-0.5 font-mono text-[11px] uppercase ${
                      f.status === "ingested"
                        ? "bg-primary/15 text-primary"
                        : f.status === "failed"
                          ? "bg-destructive/15 text-destructive"
                          : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {statusLabel(f.status)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
