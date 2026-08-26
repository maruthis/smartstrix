// Same-origin by default (dev proxy in vite.config.ts, or a reverse proxy in
// production) — set VITE_API_BASE_URL at build time to point at a backend
// served from a different origin (e.g. a separate container/deployment).
const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

function formatErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.flatMap((item) => {
      if (typeof item === "string" && item.trim()) return [item];
      if (item && typeof item === "object" && "msg" in item && typeof (item as { msg: unknown }).msg === "string") {
        return [(item as { msg: string }).msg];
      }
      return [];
    });
    if (parts.length > 0) return parts.join("; ");
  }
  return fallback;
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie.split("; ").find((item) => item.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

function csrfToken(): string | null {
  return getCookie("csrf_token") ?? getCookie("XSRF-TOKEN");
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["content-type"] = "application/json";
  const csrf = method === "GET" ? null : csrfToken();
  if (csrf) headers["x-csrf-token"] = csrf;

  const res = await fetch(`${BASE}${path}`, {
    method,
    credentials: "include",
    headers: Object.keys(headers).length > 0 ? headers : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = formatErrorDetail(data.detail, detail);
    } catch {
      // ignore
    }
    const error = new ApiError(res.status, detail);
    if (res.status === 401) unauthorizedHandler?.();
    throw error;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  delete: <T>(path: string) => request<T>("DELETE", path),
};
