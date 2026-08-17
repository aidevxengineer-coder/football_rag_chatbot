"use client";

import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { TwoFactorSetup } from "@/components/settings/TwoFactorSetup";
import { ApiError } from "@/lib/api";
import {
  API_KEY_NAMES,
  getApiKeys,
  saveApiKeys,
  type ApiKeyName,
  type ApiKeys,
} from "@/lib/settings-api";

const EMPTY_KEYS = Object.fromEntries(
  API_KEY_NAMES.map((name) => [name, ""]),
) as ApiKeys;

const SECTIONS: Array<{
  title: string;
  description: string;
  keys: ApiKeyName[];
}> = [
  {
    title: "LLM",
    description: "Required when the gateway runs with Groq.",
    keys: ["GROQ_API_KEY"],
  },
  {
    title: "Web search",
    description: "At least one provider is recommended for web search.",
    keys: ["TAVILY_API_KEY", "SERPER_API_KEY"],
  },
  {
    title: "Football data",
    description: "Connect API-Football for live match and competition data.",
    keys: ["API_FOOTBALL_KEY"],
  },
  {
    title: "Google sign-in",
    description: "OAuth credentials used by the authentication service.",
    keys: ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
  },
];

function placeholder(name: ApiKeyName): string {
  return `Enter ${name.replaceAll("_", " ").toLowerCase()}`;
}

export function SettingsView() {
  const { ready, loggedIn } = useAuth();
  const [keys, setKeys] = useState<ApiKeys>(EMPTY_KEYS);
  const [visible, setVisible] = useState<Set<ApiKeyName>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!ready) return;
    if (!loggedIn) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setError(null);
      try {
        const data = await getApiKeys();
        if (!cancelled) setKeys(data);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Could not load API keys.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, loggedIn]);

  function updateKey(name: ApiKeyName, value: string) {
    setSaved(false);
    setKeys((current) => ({ ...current, [name]: value }));
  }

  function toggleVisible(name: ApiKeyName) {
    setVisible((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      setKeys(await saveApiKeys(keys));
      setSaved(true);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not save API keys.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (ready && !loggedIn) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <h1 className="font-serif text-3xl font-bold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Sign in to manage provider and OAuth keys.
        </p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl px-6 py-10 md:px-10">
        <h1 className="font-serif text-3xl font-bold">Settings</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          API keys used for LLM calls, web search, football data, and Google
          sign-in. Values are stored in the server{" "}
          <code className="font-mono text-xs">.env</code>.
        </p>

        <div className="mt-8">
          <TwoFactorSetup />
        </div>

        <form className="mt-5 space-y-5" onSubmit={submit}>
          {SECTIONS.map((section) => (
            <section
              key={section.title}
              className="rounded-xl border border-border bg-card p-5"
            >
              <h2 className="font-serif text-lg font-semibold">
                {section.title}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {section.description}
              </p>
              <div className="mt-4 space-y-4">
                {section.keys.map((name) => (
                  <label key={name} className="block space-y-1.5">
                    <span className="font-mono text-xs text-muted-foreground">
                      {name}
                    </span>
                    <span className="relative block">
                      <input
                        type={visible.has(name) ? "text" : "password"}
                        value={keys[name]}
                        onChange={(event) => updateKey(name, event.target.value)}
                        disabled={loading || saving}
                        autoComplete="off"
                        spellCheck={false}
                        className="h-10 w-full rounded-md border border-border bg-background px-3 pr-10 font-mono text-sm outline-none focus:border-ring focus:ring-1 focus:ring-ring disabled:opacity-60"
                        placeholder={loading ? "Loading…" : placeholder(name)}
                      />
                      <button
                        type="button"
                        onClick={() => toggleVisible(name)}
                        className="absolute right-1 top-1 inline-flex h-8 w-8 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
                        aria-label={`${visible.has(name) ? "Hide" : "Show"} ${name}`}
                      >
                        <span className="material-symbols-outlined text-[18px]">
                          {visible.has(name) ? "visibility_off" : "visibility"}
                        </span>
                      </button>
                    </span>
                  </label>
                ))}
              </div>
            </section>
          ))}

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          {saved && (
            <div
              className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-3 text-sm text-foreground"
              role="status"
            >
              Keys saved. Restart the affected services to apply changes.
            </div>
          )}

          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={loading || saving}
              className="rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save keys"}
            </button>
            <span className="text-xs text-muted-foreground">
              Changes merge into the existing .env file.
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}
