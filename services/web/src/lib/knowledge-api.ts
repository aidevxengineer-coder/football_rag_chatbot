import { ApiError, apiJson, getApiBase } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";

type Data<T> = { data: T };

export type KnowledgeStats = {
  chunks: number;
  files: number;
  memory_tokens: number;
};

export type KnowledgeFile = {
  id: string;
  filename: string;
  content_hash: string;
  status: string;
  error_message: string | null;
  chunks_indexed: number;
  tokens_indexed: number;
  created_at: string;
};

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  if (!token) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${token}` };
}

export async function fetchKnowledgeStats(): Promise<KnowledgeStats> {
  const res = await apiJson<Data<KnowledgeStats>>("/knowledge/stats", {
    headers: authHeaders(),
  });
  return res.data;
}

export async function listKnowledgeFiles(): Promise<KnowledgeFile[]> {
  const res = await apiJson<Data<KnowledgeFile[]>>("/knowledge/files", {
    headers: authHeaders(),
  });
  return res.data;
}

export async function uploadKnowledgeFile(file: File): Promise<KnowledgeFile> {
  const token = getAccessToken();
  if (!token) throw new Error("Not authenticated");
  const form = new FormData();
  form.append("file", file);
  const base = getApiBase();
  const url = `${base}/knowledge/files`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: form,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = body as { error?: { code?: string; message?: string } };
    throw new ApiError(
      res.status,
      err.error?.code || "REQUEST_FAILED",
      err.error?.message || res.statusText || "Upload failed",
    );
  }
  return (body as Data<KnowledgeFile>).data;
}

export { ApiError };
