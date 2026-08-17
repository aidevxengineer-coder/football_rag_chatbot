import { apiJson } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

type Data<T> = { data: T };

export const API_KEY_NAMES = [
  "GROQ_API_KEY",
  "TAVILY_API_KEY",
  "SERPER_API_KEY",
  "API_FOOTBALL_KEY",
  "GOOGLE_CLIENT_ID",
  "GOOGLE_CLIENT_SECRET",
] as const;

export type ApiKeyName = (typeof API_KEY_NAMES)[number];
export type ApiKeys = Record<ApiKeyName, string>;

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  if (!token) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${token}` };
}

export async function getApiKeys(): Promise<ApiKeys> {
  const response = await apiJson<Data<ApiKeys>>("/settings/api-keys", {
    headers: authHeaders(),
  });
  return response.data;
}

export async function saveApiKeys(keys: ApiKeys): Promise<ApiKeys> {
  const response = await apiJson<Data<ApiKeys>>("/settings/api-keys", {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(keys),
  });
  return response.data;
}
