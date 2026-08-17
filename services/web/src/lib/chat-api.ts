import { ApiError, apiJson } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

type Data<T> = { data: T };

export type ChatListItem = {
  id: string;
  project_id: string | null;
  title: string;
  updated_at: string;
};

export type ChatResponse = {
  id: string;
  user_id: string | null;
  project_id: string | null;
  title: string;
  compression_pending: boolean;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  id: string;
  role: string;
  content: string;
  created_at: string;
};

export type PostMessageResult = {
  message: ChatMessage;
  assistant_message: ChatMessage | null;
  run_id: number | null;
  tool_notice: string | null;
  tool_notice_code: string | null;
  web_search_skipped: boolean;
};

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function createChat(title = "New Chat"): Promise<ChatResponse> {
  const res = await apiJson<Data<ChatResponse>>("/chats", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ title }),
  });
  return res.data;
}

export async function listChats(limit = 40): Promise<ChatListItem[]> {
  const res = await apiJson<Data<ChatListItem[]>>(
    `/chats?limit=${limit}&sort=-updated_at`,
    { headers: authHeaders() },
  );
  return res.data;
}

export async function getChat(chatId: string): Promise<ChatResponse> {
  const res = await apiJson<Data<ChatResponse>>(`/chats/${chatId}`, {
    headers: authHeaders(),
  });
  return res.data;
}

export async function listMessages(chatId: string): Promise<ChatMessage[]> {
  const res = await apiJson<Data<{ messages: ChatMessage[] }>>(
    `/chats/${chatId}/messages`,
    { headers: authHeaders() },
  );
  return res.data.messages;
}

export async function postMessage(
  chatId: string,
  content: string,
  webSearchEnabled = false,
): Promise<PostMessageResult> {
  const res = await apiJson<Data<PostMessageResult>>(
    `/chats/${chatId}/messages`,
    {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({
        role: "user",
        content,
        web_search_enabled: webSearchEnabled,
      }),
    },
  );
  return res.data;
}

export async function mergeChat(chatId: string): Promise<ChatResponse> {
  const res = await apiJson<Data<ChatResponse>>("/chats/merge", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ chat_id: chatId }),
  });
  return res.data;
}

export function isLoginRequired(err: unknown): boolean {
  return err instanceof ApiError && err.code === "LOGIN_REQUIRED";
}
