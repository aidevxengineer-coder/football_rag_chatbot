import { apiJson, getApiBase } from "@/lib/api";
import {
  clearSession,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setRefreshToken,
} from "@/lib/auth";

export type User = {
  id: string;
  email: string;
  first_name: string;
  status: string;
  totp_enabled: boolean;
};

type Data<T> = { data: T };

export type RegisterResult = {
  user_id: string;
  email: string;
  first_name: string;
  status: string;
  verification_token: string;
  verification_email_sent?: boolean;
  dev_verification_code?: string | null;
  verification_email_error?: string | null;
};

export type LoginResult = {
  requires_2fa: boolean;
  step_up_token?: string | null;
  access_token?: string | null;
  refresh_token?: string | null;
  expires_in?: number | null;
  token_type?: string | null;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
};

export type Enable2FAResult = {
  secret_uri: string;
  recovery_codes: string[];
};

function authHeader(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export async function registerUser(input: {
  email: string;
  password: string;
  first_name: string;
}): Promise<RegisterResult> {
  const res = await apiJson<Data<RegisterResult>>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return res.data;
}

export async function verifyEmail(
  verificationToken: string,
  code: string,
): Promise<TokenPair> {
  const res = await apiJson<Data<TokenPair>>("/auth/verify-email", {
    method: "POST",
    headers: authHeader(verificationToken),
    body: JSON.stringify({ code }),
  });
  return res.data;
}

export async function loginUser(input: {
  email: string;
  password: string;
}): Promise<LoginResult> {
  const res = await apiJson<Data<LoginResult>>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return res.data;
}

export async function enable2FA(setupOrAccessToken: string): Promise<Enable2FAResult> {
  const res = await apiJson<Data<Enable2FAResult>>("/auth/2fa/enable", {
    method: "POST",
    headers: authHeader(setupOrAccessToken),
  });
  return res.data;
}

export async function verify2FA(
  stepUpOrSetupToken: string,
  code: string,
): Promise<TokenPair> {
  const res = await apiJson<Data<TokenPair>>("/auth/2fa/verify", {
    method: "POST",
    headers: authHeader(stepUpOrSetupToken),
    body: JSON.stringify({ code }),
  });
  return res.data;
}

export async function fetchMe(accessToken?: string): Promise<User> {
  const token = accessToken || getAccessToken();
  if (!token) throw new Error("Not authenticated");
  const res = await apiJson<Data<User>>("/auth/me", {
    headers: authHeader(token),
  });
  return res.data;
}

export async function logoutUser(): Promise<void> {
  const token = getAccessToken();
  if (token) {
    try {
      await apiJson<void>("/auth/logout", {
        method: "POST",
        headers: authHeader(token),
      });
    } catch {
      // still clear local session
    }
  }
  clearSession();
}

export async function refreshTokens(): Promise<TokenPair | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;
  try {
    const res = await apiJson<Data<TokenPair>>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refresh }),
    });
    setAccessToken(res.data.access_token);
    setRefreshToken(res.data.refresh_token);
    return res.data;
  } catch {
    clearSession();
    return null;
  }
}

export function persistTokens(tokens: TokenPair): void {
  setAccessToken(tokens.access_token);
  setRefreshToken(tokens.refresh_token);
}

export function googleOAuthUrl(): string {
  return `${getApiBase()}/auth/oauth/google`;
}

export async function fetchOAuthProviders(): Promise<{ google: boolean }> {
  const res = await apiJson<Data<{ google: boolean }>>("/auth/oauth/providers");
  return res.data;
}
