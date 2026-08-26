import { vi } from "vitest";

interface MockResponse {
  status?: number;
  body?: unknown;
  ok?: boolean;
}

/** Stubs global fetch to return the given response(s) in order. The last
 * response repeats once the queue is exhausted, so callers only need to
 * enumerate distinct responses. */
export function mockFetchJson(responses: MockResponse | MockResponse[]) {
  const queue = Array.isArray(responses) ? [...responses] : [responses];
  const fn = vi.fn(async (_url: string, _init?: RequestInit) => {
    const next = queue.length > 1 ? queue.shift()! : queue[0];
    const status = next.status ?? 200;
    const ok = next.ok ?? (status >= 200 && status < 300);
    return {
      ok,
      status,
      statusText: "error",
      json: async () => next.body,
    } as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** Stubs global fetch with a custom implementation for per-call routing by
 * method/URL (e.g. different responses for GET vs POST to the same path). */
export function mockFetchImpl(impl: (url: string, init?: RequestInit) => Promise<Partial<Response>>) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => impl(url, init));
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** Delays a response by a tick so a caller can observe a mutation's
 * intermediate `isPending` UI state before it resolves. */
export function delay<T>(value: T, ms = 20): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}
