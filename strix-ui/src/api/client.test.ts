import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";
import { mockFetchJson } from "../test/mock-fetch";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api.get", () => {
  it("sends credentials and no body, returns parsed JSON", async () => {
    const fetchMock = mockFetchJson({ body: { hello: "world" } });
    const result = await api.get<{ hello: string }>("/api/thing");
    expect(result).toEqual({ hello: "world" });

    const [, init] = fetchMock.mock.calls[0];
    if (!init) throw new Error("expected init");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("include");
    expect(init.headers).toBeUndefined();
    expect(init.body).toBeUndefined();
  });
});

describe("api.post / patch", () => {
  it("sends a JSON body with content-type header", async () => {
    const fetchMock = mockFetchJson({ body: { ok: true } });
    await api.post("/api/thing", { name: "x" });

    const [, init] = fetchMock.mock.calls[0];
    if (!init) throw new Error("expected init");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "content-type": "application/json" });
    expect(init.body).toBe(JSON.stringify({ name: "x" }));
  });

  it("defaults to an empty object body when none is given", async () => {
    const fetchMock = mockFetchJson({ body: { ok: true } });
    await api.post("/api/thing");
    const [, init] = fetchMock.mock.calls[0];
    if (!init) throw new Error("expected init");
    expect(init.body).toBe("{}");
  });

  it("patch behaves like post", async () => {
    const fetchMock = mockFetchJson({ body: { ok: true } });
    await api.patch("/api/thing", { a: 1 });
    const [, init] = fetchMock.mock.calls[0];
    if (!init) throw new Error("expected init");
    expect(init.method).toBe("PATCH");
  });
});

describe("api.delete", () => {
  it("sends no body", async () => {
    const fetchMock = mockFetchJson({ body: { ok: true } });
    await api.delete("/api/thing/1");
    const [, init] = fetchMock.mock.calls[0];
    if (!init) throw new Error("expected init");
    expect(init.method).toBe("DELETE");
    expect(init.body).toBeUndefined();
  });
});

describe("error handling", () => {
  it("throws ApiError with the server-provided detail", async () => {
    mockFetchJson({ status: 404, body: { detail: "not_found" } });
    await expect(api.get("/api/thing")).rejects.toMatchObject({ status: 404, detail: "not_found" });
  });

  it("flattens FastAPI validation error objects into readable text", async () => {
    mockFetchJson({
      status: 422,
      body: { detail: [{ loc: ["body", "url"], msg: "invalid_webhook_url", type: "value_error" }] },
    });
    await expect(api.get("/api/thing")).rejects.toMatchObject({ detail: "invalid_webhook_url" });
  });

  it("is an instance of ApiError and Error", async () => {
    mockFetchJson({ status: 400, body: { detail: "bad_request" } });
    try {
      await api.get("/api/thing");
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err).toBeInstanceOf(Error);
    }
  });

  it("falls back to statusText when the error body isn't valid JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => {
          throw new SyntaxError("not json");
        },
      }))
    );
    await expect(api.get("/api/thing")).rejects.toMatchObject({ status: 500, detail: "Internal Server Error" });
  });

  it("falls back to statusText when the error body has no detail field", async () => {
    mockFetchJson({ status: 500, body: { message: "oops" } });
    await expect(api.get("/api/thing")).rejects.toMatchObject({ detail: "error" });
  });
});

describe("204 No Content", () => {
  it("returns undefined without parsing a body", async () => {
    mockFetchJson({ status: 204, body: null });
    const result = await api.delete("/api/thing/1");
    expect(result).toBeUndefined();
  });
});
