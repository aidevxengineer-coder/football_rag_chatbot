"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useMatchStatus } from "@/components/chat/MatchStatusContext";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { formatApiError } from "@/lib/api";
import { createChat, isLoginRequired, postMessage } from "@/lib/chat-api";
import { getAccessToken, setAnonChatId } from "@/lib/auth";
import { pipelineWsUrl } from "@/lib/ws";

export function HomeKickoff() {
  const router = useRouter();
  const { setOptimisticStart, applyEvent, setRunning } = useMatchStatus();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSend(content: string, webSearchEnabled: boolean) {
    setError(null);
    setPending(true);
    try {
      const chat = await createChat(
        content.length > 48 ? `${content.slice(0, 48)}…` : content,
      );
      if (!getAccessToken()) {
        setAnonChatId(chat.id);
      }
      setOptimisticStart();
      const ws = new WebSocket(pipelineWsUrl(chat.id));
      ws.onmessage = (ev) => {
        try {
          applyEvent(JSON.parse(ev.data) as Record<string, unknown>);
        } catch {
          // ignore
        }
      };
      try {
        await postMessage(chat.id, content, webSearchEnabled);
      } finally {
        ws.close();
      }
      router.push(`/chat/${chat.id}`);
    } catch (err) {
      setRunning(false);
      if (isLoginRequired(err)) {
        setError("Sign in to continue.");
        router.push("/?auth=signin");
      } else {
        setError(formatApiError(err));
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
        <h1 className="font-serif text-3xl font-bold text-foreground">
          Ready for kickoff
        </h1>
        <p className="max-w-md text-muted-foreground">
          Ask a tactical question or start a new match thread from Kickoff.
        </p>
        {error && (
          <pre className="whitespace-pre-wrap text-sm text-destructive">{error}</pre>
        )}
      </div>
      <ChatComposer pending={pending} onSend={onSend} />
    </div>
  );
}
