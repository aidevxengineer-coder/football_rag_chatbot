"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  clearAnonChatId,
  getAccessToken,
  getAnonChatId,
  isLoggedIn as hasAccessToken,
} from "@/lib/auth";
import {
  fetchMe,
  logoutUser,
  persistTokens,
  refreshTokens,
  type TokenPair,
  type User,
} from "@/lib/auth-api";
import { mergeChat } from "@/lib/chat-api";

type AuthContextValue = {
  ready: boolean;
  user: User | null;
  loggedIn: boolean;
  refreshMe: () => Promise<void>;
  applyTokens: (tokens: TokenPair) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  const refreshMe = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      return;
    }
    try {
      const me = await fetchMe();
      setUser(me);
    } catch {
      const refreshed = await refreshTokens();
      if (!refreshed) {
        setUser(null);
        return;
      }
      try {
        setUser(await fetchMe());
      } catch {
        setUser(null);
      }
    }
  }, []);

  const applyTokens = useCallback(async (tokens: TokenPair) => {
    persistTokens(tokens);
    const anonId = getAnonChatId();
    if (anonId) {
      try {
        await mergeChat(anonId);
        clearAnonChatId();
      } catch {
        // Keep anon id so user can retry; chat may already be claimed.
      }
    }
    await refreshMe();
  }, [refreshMe]);

  const logout = useCallback(async () => {
    await logoutUser();
    setUser(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (hasAccessToken()) {
        await refreshMe();
      }
      if (!cancelled) setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshMe]);

  const value = useMemo<AuthContextValue>(
    () => ({
      ready,
      user,
      loggedIn: Boolean(user),
      refreshMe,
      applyTokens,
      logout,
    }),
    [ready, user, refreshMe, applyTokens, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
