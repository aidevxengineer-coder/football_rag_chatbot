"use client";

const ACCESS_KEY = "pitchside_access_token";
const REFRESH_KEY = "pitchside_refresh_token";
const ANON_CHAT_KEY = "pitchside_anon_chat_id";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(ACCESS_KEY);
}

export function setAccessToken(token: string): void {
  sessionStorage.setItem(ACCESS_KEY, token);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

export function setRefreshToken(token: string): void {
  localStorage.setItem(REFRESH_KEY, token);
}

export function clearRefreshToken(): void {
  localStorage.removeItem(REFRESH_KEY);
}

export function getAnonChatId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ANON_CHAT_KEY);
}

export function setAnonChatId(id: string): void {
  localStorage.setItem(ANON_CHAT_KEY, id);
}

export function clearAnonChatId(): void {
  localStorage.removeItem(ANON_CHAT_KEY);
}

export function isLoggedIn(): boolean {
  return Boolean(getAccessToken());
}

export function clearSession(): void {
  clearAccessToken();
  clearRefreshToken();
}
