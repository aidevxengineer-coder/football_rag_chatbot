"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMatchStatus } from "@/components/chat/MatchStatusContext";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { MessageContent } from "@/components/chat/MessageContent";
import { formatApiError } from "@/lib/api";
import {
  getChat,
  isLoginRequired,
  listMessages,
  postMessage,
  type ChatMessage,
} from "@/lib/chat-api";
import { pipelineWsUrl } from "@/lib/ws";

type ChatThreadProps = {
  chatId: string;
};

function isPipelineInFlight(messages: ChatMessage[]): boolean {
  const last = messages[messages.length - 1];
  return last?.role === "user";
}

export function ChatThread({ chatId }: ChatThreadProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { setOptimisticStart, applyEvent, resetStages, setRunning } =
    useMatchStatus();

  const [title, setTitle] = useState("Match thread");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const assistantIdsRef = useRef<Set<string>>(new Set());

  const syncMessages = useCallback(async () => {
    const synced = await listMessages(chatId);
    setMessages((prev) => (synced.length > 0 ? synced : prev));
    return synced;
  }, [chatId]);

  const finishPipeline = useCallback(
    async (notice?: string) => {
      try {
        await syncMessages();
      } catch {
        // Keep the current thread visible if refresh fails.
      }
      setPending(false);
      setRunning(false);
      if (notice) {
        setError(notice);
      }
    },
    [setRunning, syncMessages],
  );

  const appendAssistantReply = useCallback((reply: string) => {
    const trimmed = reply.trim();
    if (!trimmed) return;
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last?.role === "assistant" && last.content === trimmed) {
        return prev;
      }
      const id = `ws-${Date.now()}`;
      if (assistantIdsRef.current.has(id)) return prev;
      assistantIdsRef.current.add(id);
      return [
        ...prev,
        {
          id,
          role: "assistant",
          content: trimmed,
          created_at: new Date().toISOString(),
        },
      ];
    });
  }, []);

  const openAuth = useCallback(() => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("auth", "signin");
    router.push(`${pathname}?${params.toString()}`);
  }, [pathname, router, searchParams]);

  const ensureWs = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
      return wsRef.current;
    }
    const ws = new WebSocket(pipelineWsUrl(chatId));
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as Record<string, unknown>;
        applyEvent(data);
        if (data.type === "pipeline_complete" && typeof data.reply === "string") {
          void finishPipeline();
        }
        if (data.type === "pipeline_error" && typeof data.message === "string") {
          void finishPipeline(data.message);
        }
      } catch {
        // ignore malformed frames
      }
    };
    wsRef.current = ws;
    return ws;
  }, [applyEvent, chatId, finishPipeline]);

  useEffect(() => {
    let cancelled = false;
    resetStages();
    setInitialLoading(true);
    setError(null);

    (async () => {
      try {
        const [chatResult, messageResult] = await Promise.allSettled([
          getChat(chatId),
          listMessages(chatId),
        ]);
        if (cancelled) return;

        if (chatResult.status === "fulfilled") {
          setTitle(chatResult.value.title || "Match thread");
        }

        if (messageResult.status === "fulfilled") {
          const msgs = messageResult.value;
          setMessages(msgs);
          if (isPipelineInFlight(msgs)) {
            setPending(true);
            setRunning(true);
            ensureWs();
          }
        } else if (chatResult.status === "rejected") {
          throw chatResult.reason;
        } else {
          throw messageResult.reason;
        }
      } catch (err) {
        if (cancelled) return;
        if (isLoginRequired(err)) {
          openAuth();
          setError("Sign in to continue this match.");
        } else {
          setError(formatApiError(err));
        }
      } finally {
        if (!cancelled) setInitialLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [chatId, ensureWs, openAuth, resetStages, setRunning]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending]);

  async function onSend(content: string, webSearchEnabled: boolean) {
    setError(null);
    setPending(true);
    const optimistic: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setOptimisticStart();
    ensureWs();

    let waitForPipeline = false;

    try {
      const result = await postMessage(chatId, content, webSearchEnabled);
      setMessages((prev) => {
        const withoutOptimistic = prev.filter((m) => m.id !== optimistic.id);
        const next = [...withoutOptimistic, result.message];
        if (result.assistant_message) {
          assistantIdsRef.current.add(result.assistant_message.id);
          next.push(result.assistant_message);
        }
        return next;
      });
      waitForPipeline =
        result.tool_notice_code === "PIPELINE_RUNNING" ||
        (!result.assistant_message && !result.tool_notice);
      if (result.assistant_message) {
        setRunning(false);
      } else if (result.tool_notice && result.tool_notice_code !== "PIPELINE_RUNNING") {
        setError(result.tool_notice);
        setRunning(false);
      }
    } catch (err) {
      setRunning(false);
      try {
        const synced = await listMessages(chatId);
        setMessages((prev) => {
          const optimisticMsg = prev.find((m) => m.id === optimistic.id);
          const hasUserMessage = synced.some(
            (m) => m.role === "user" && m.content === content,
          );
          if (hasUserMessage) return synced;
          return optimisticMsg ? [...synced, optimisticMsg] : synced.length > 0 ? synced : prev;
        });
      } catch {
        // Keep optimistic user message in place.
      }
      if (isLoginRequired(err)) {
        setError("Anonymous message limit reached. Sign in to continue.");
        openAuth();
      } else {
        setError(formatApiError(err));
      }
    } finally {
      if (!waitForPipeline) {
        setPending(false);
      }
    }
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <header className="border-b border-border px-6 py-4">
        <p className="font-mono text-xs uppercase text-muted-foreground">Chat</p>
        <h1 className="mt-1 font-serif text-2xl font-bold">{title}</h1>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {initialLoading && messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">Loading match thread…</p>
        ) : messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <h2 className="font-serif text-2xl font-bold">Ready for kickoff</h2>
            <p className="max-w-md text-sm text-muted-foreground">
              Ask a tactical question to start the analysis pipeline.
            </p>
          </div>
        ) : (
          <ul className="mx-auto flex max-w-3xl flex-col gap-4">
            {messages.map((m) => (
              <li
                key={m.id}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "border border-border bg-card text-card-foreground"
                  }`}
                >
                  <MessageContent content={m.content} role={m.role} />
                </div>
              </li>
            ))}
            {pending && (
              <li className="flex justify-start">
                <div className="rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
                  Analyzing…
                </div>
              </li>
            )}
            <div ref={bottomRef} />
          </ul>
        )}
        {error && (
          <pre className="mx-auto mt-4 max-w-3xl whitespace-pre-wrap text-center text-sm text-destructive">
            {error}
          </pre>
        )}
      </div>

      <ChatComposer pending={pending || initialLoading} onSend={onSend} />
    </div>
  );
}
