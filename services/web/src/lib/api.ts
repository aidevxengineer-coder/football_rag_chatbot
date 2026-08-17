/** Browser-facing API base. Prefer same-origin `/api` rewrite when set. */
export function getApiBase(): string {
  if (typeof window !== "undefined") {
    return "/api";
  }
  return (
    process.env.API_URL?.replace(/\/$/, "") ||
    "http://localhost:8000"
  );
}

export type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
  detail?: string | Array<{ msg?: string; loc?: unknown[] }>;
};

export class ApiError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: unknown,
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function formatValidationDetail(
  detail: Array<{ msg?: string; loc?: unknown[] }>,
): string {
  return detail
    .map((item) => {
      const path = Array.isArray(item.loc)
        ? item.loc.filter((part) => part !== "body").join(".")
        : "";
      return path ? `${path}: ${item.msg || "invalid"}` : item.msg || "invalid";
    })
    .join("; ");
}

export function parseApiErrorBody(
  body: unknown,
  status: number,
  statusText: string,
): { code: string; message: string; details?: unknown } {
  if (body && typeof body === "object") {
    const payload = body as ApiErrorBody;
    if (payload.error?.message) {
      return {
        code: payload.error.code || "REQUEST_FAILED",
        message: payload.error.message,
        details: payload.error.details,
      };
    }
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return {
        code: "REQUEST_FAILED",
        message: payload.detail,
      };
    }
    if (Array.isArray(payload.detail) && payload.detail.length > 0) {
      return {
        code: "VALIDATION_ERROR",
        message: formatValidationDetail(payload.detail),
        details: payload.detail,
      };
    }
  }
  return {
    code: "REQUEST_FAILED",
    message: statusText || "Request failed",
  };
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const base = getApiBase();
  const url = path.startsWith("http")
    ? path
    : `${base}${path.startsWith("/") ? path : `/${path}`}`;
  return fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers || {}),
    },
  });
}

export async function apiJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await apiFetch(path, init);
  if (res.status === 204) {
    return undefined as T;
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const parsed = parseApiErrorBody(body, res.status, res.statusText);
    throw new ApiError(
      res.status,
      parsed.code,
      parsed.message,
      parsed.details,
    );
  }
  return body as T;
}

export function formatApiError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "Request failed";
  }
  if (!err.details) return err.message;
  if (process.env.NODE_ENV === "production") return err.message;
  try {
    const details = JSON.stringify(err.details, null, 2);
    return `${err.message}\n\n${details}`;
  } catch {
    return err.message;
  }
}
