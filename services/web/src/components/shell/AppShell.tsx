"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AuthModal } from "@/components/auth/AuthModal";
import { useAuth } from "@/components/auth/AuthProvider";
import { MatchStatusProvider } from "@/components/chat/MatchStatusContext";
import { MatchStatusPanel } from "@/components/chat/MatchStatusPanel";
import {
  createChat,
  listChats,
  type ChatListItem,
} from "@/lib/chat-api";
import {
  getAccessToken,
  getAnonChatId,
  setAnonChatId,
} from "@/lib/auth";
import { formatRelativeTime } from "@/lib/time";

const nav = [
  { href: "/leagues", label: "Leagues", icon: "emoji_events", authRequired: true },
  { href: "/knowledge", label: "Ball Knowledge", icon: "library_add", authRequired: true },
  { href: "/live-events", label: "Live Events", icon: "sensors" },
  { href: "/settings", label: "Settings", icon: "settings", authOnly: true },
] as const;

type AppShellProps = {
  children: ReactNode;
  showMatchStatus?: boolean;
};

export function AppShell({ children, showMatchStatus = false }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { loggedIn, ready, user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const [history, setHistory] = useState<ChatListItem[]>([]);
  const [kickoffPending, setKickoffPending] = useState(false);

  const refreshHistory = useCallback(async () => {
    if (!ready) return;
    if (loggedIn) {
      try {
        setHistory(await listChats());
      } catch {
        setHistory([]);
      }
      return;
    }
    const anonId = getAnonChatId();
    if (anonId) {
      setHistory([
        {
          id: anonId,
          project_id: null,
          title: "Guest match",
          updated_at: new Date().toISOString(),
        },
      ]);
    } else {
      setHistory([]);
    }
  }, [loggedIn, ready]);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory, pathname]);

  useEffect(() => {
    if (!ready) return;
    const gated =
      pathname.startsWith("/settings") ||
      pathname.startsWith("/knowledge") ||
      pathname.startsWith("/leagues");
    if (gated && !loggedIn) {
      const params = new URLSearchParams(searchParams.toString());
      params.set("auth", pathname.startsWith("/leagues") ? "signin" : "signup");
      router.replace(`${pathname}?${params.toString()}`);
    }
  }, [ready, loggedIn, pathname, router, searchParams]);

  function openAuth(mode: "signup" | "signin") {
    const params = new URLSearchParams(searchParams.toString());
    params.set("auth", mode);
    router.push(`${pathname}?${params.toString()}`);
  }

  async function onAuthCta() {
    if (loggedIn) {
      await logout();
      return;
    }
    openAuth("signup");
  }

  async function onKickoff() {
    if (kickoffPending) return;
    if (!loggedIn) {
      const existing = getAnonChatId();
      if (existing) {
        router.push(`/chat/${existing}`);
        return;
      }
    }
    setKickoffPending(true);
    try {
      const chat = await createChat("New Chat");
      if (!getAccessToken()) {
        setAnonChatId(chat.id);
      }
      await refreshHistory();
      router.push(`/chat/${chat.id}`);
    } catch {
      openAuth("signin");
    } finally {
      setKickoffPending(false);
    }
  }

  const shell = (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <aside
        className={`flex h-full shrink-0 flex-col border-r border-sidebar-border bg-sidebar/90 p-4 transition-[width] duration-200 ${
          collapsed ? "w-[88px]" : "w-[280px]"
        }`}
      >
        <div className="mb-6 flex items-center justify-between gap-2">
          {!collapsed && (
            <Link href="/" className="font-serif text-2xl font-bold text-primary">
              Pitchside
            </Link>
          )}
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-sidebar-border text-muted-foreground hover:border-ring hover:text-foreground"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setCollapsed((v) => !v)}
          >
            <span className="material-symbols-outlined text-[18px]">
              {collapsed ? "left_panel_open" : "left_panel_close"}
            </span>
          </button>
        </div>

        <button
          type="button"
          onClick={onKickoff}
          disabled={kickoffPending}
          className="mb-6 flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 font-semibold text-primary-foreground disabled:opacity-70"
        >
          <span className="material-symbols-outlined text-[22px]">sports</span>
          {!collapsed && <span>{kickoffPending ? "Starting…" : "Kickoff"}</span>}
        </button>

        <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
          {!collapsed && (
            <p className="mb-2 font-mono text-xs uppercase text-muted-foreground">
              Match History
            </p>
          )}
          {!collapsed && history.length === 0 && (
            <p className="mb-4 px-2 text-sm text-muted-foreground">
              No matches yet — hit Kickoff to start.
            </p>
          )}
          {!collapsed &&
            history.map((item) => {
              const active = pathname === `/chat/${item.id}`;
              return (
                <Link
                  key={item.id}
                  href={`/chat/${item.id}`}
                  className={`mb-1 flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
                    active
                      ? "bg-sidebar-accent/30 text-primary"
                      : "text-sidebar-foreground hover:bg-muted"
                  }`}
                >
                  <span className="truncate">{item.title || "Untitled"}</span>
                  <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                    {formatRelativeTime(item.updated_at)}
                  </span>
                </Link>
              );
            })}

          {nav
            .filter((item) => !("authOnly" in item && item.authOnly) || loggedIn)
            .map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2.5 font-mono text-sm transition-colors ${
                    active
                      ? "bg-sidebar-accent/30 text-primary"
                      : "text-sidebar-foreground hover:bg-muted"
                  } ${collapsed ? "justify-center" : ""}`}
                  onClick={(e) => {
                    if ("authRequired" in item && item.authRequired && !loggedIn) {
                      e.preventDefault();
                      openAuth("signup");
                    }
                  }}
                >
                  <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                  {!collapsed && <span>{item.label}</span>}
                </Link>
              );
            })}

          <div className="mt-auto space-y-1 border-t border-sidebar-border pt-4">
            {user && !collapsed && (
              <p className="mb-2 px-2 text-xs text-muted-foreground">
                Signed in as {user.first_name}
              </p>
            )}
            <Link
              href="/help"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 font-mono text-sm text-sidebar-foreground hover:bg-muted ${
                collapsed ? "justify-center" : ""
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">help</span>
              {!collapsed && <span>Help</span>}
            </Link>
            <button
              type="button"
              onClick={onAuthCta}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 font-mono text-sm text-sidebar-foreground hover:bg-muted ${
                collapsed ? "justify-center" : ""
              }`}
            >
              <span className="material-symbols-outlined text-[20px]">
                {loggedIn ? "logout" : "person_add"}
              </span>
              {!collapsed && <span>{loggedIn ? "Logout" : "Sign up"}</span>}
            </button>
          </div>
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1">
        <main className="min-w-0 flex-1 overflow-hidden">{children}</main>
        {showMatchStatus && <MatchStatusPanel />}
      </div>

      <AuthModal />
    </div>
  );

  if (showMatchStatus) {
    return <MatchStatusProvider>{shell}</MatchStatusProvider>;
  }
  return shell;
}
