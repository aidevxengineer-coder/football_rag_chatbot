"use client";

import { FormEvent, useState } from "react";

type ChatComposerProps = {
  disabled?: boolean;
  pending?: boolean;
  placeholder?: string;
  onSend: (content: string, webSearchEnabled: boolean) => Promise<void> | void;
};

export function ChatComposer({
  disabled,
  pending,
  placeholder = "Ask Pitchside…",
  onSend,
}: ChatComposerProps) {
  const [text, setText] = useState("");
  const [webSearch, setWebSearch] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const content = text.trim();
    if (!content || disabled || pending) return;
    setText("");
    await onSend(content, webSearch);
  }

  return (
    <div className="border-t border-border p-4">
      <form
        onSubmit={submit}
        className="mx-auto flex max-w-3xl items-center gap-2 rounded-full border border-border bg-card px-4 py-2"
      >
        <input
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground disabled:opacity-60"
          placeholder={placeholder}
          value={text}
          disabled={disabled || pending}
          onChange={(e) => setText(e.target.value)}
          aria-label="Message"
        />
        <button
          type="button"
          aria-pressed={webSearch}
          title="Web search"
          onClick={() => setWebSearch((v) => !v)}
          className={`inline-flex h-8 w-8 items-center justify-center rounded-full border text-sm transition-colors ${
            webSearch
              ? "border-primary bg-primary/15 text-primary"
              : "border-border text-muted-foreground hover:border-ring hover:text-foreground"
          }`}
        >
          <span className="material-symbols-outlined text-[18px]">travel_explore</span>
        </button>
        <button
          type="submit"
          disabled={disabled || pending || !text.trim()}
          className="rounded-full bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground disabled:opacity-60"
        >
          {pending ? "…" : "Send"}
        </button>
      </form>
      <p className="mt-2 text-center font-mono text-[11px] text-muted-foreground/70">
        AI analysis can make mistakes. Verify critical match data.
        {webSearch ? " · Web search on" : ""}
      </p>
    </div>
  );
}
