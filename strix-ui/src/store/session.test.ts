import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSession, setSessionBoundaryHandler } from "./session";
import { mockFetchJson } from "../test/mock-fetch";
import type { MeOut } from "../api/types";

const ME: MeOut = {
  user: { id: "u1", email: "a@example.com", name: "A", two_factor_enabled: false },
  active_org: { id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" },
  role: "admin",
  organizations: [{ id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" }],
};

beforeEach(() => {
  useSession.setState({ me: null, loading: false, loaded: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
  setSessionBoundaryHandler(null);
});

describe("useSession", () => {
  it("setMe sets the user and marks loaded", () => {
    useSession.getState().setMe(ME);
    expect(useSession.getState().me).toEqual(ME);
    expect(useSession.getState().loaded).toBe(true);
  });

  it("refresh populates me on success", async () => {
    mockFetchJson({ body: ME });
    await useSession.getState().refresh();
    expect(useSession.getState().me).toEqual(ME);
    expect(useSession.getState().loading).toBe(false);
    expect(useSession.getState().loaded).toBe(true);
  });

  it("refresh clears me on failure (e.g. not authenticated)", async () => {
    mockFetchJson({ status: 401, body: { detail: "not_authenticated" } });
    useSession.setState({ me: ME });
    await useSession.getState().refresh();
    expect(useSession.getState().me).toBeNull();
    expect(useSession.getState().loaded).toBe(true);
  });

  it("switchOrg updates me with the response and notifies the session boundary", async () => {
    const crossed = vi.fn();
    setSessionBoundaryHandler(crossed);
    const switched = { ...ME, active_org: { id: "org2", name: "Other", created_at: "2026-01-01T00:00:00Z" } };
    mockFetchJson({ body: switched });
    await useSession.getState().switchOrg("org2");
    expect(useSession.getState().me?.active_org?.id).toBe("org2");
    expect(crossed).toHaveBeenCalledOnce();
  });

  it("logout clears me and notifies the session boundary", async () => {
    const crossed = vi.fn();
    setSessionBoundaryHandler(crossed);
    useSession.setState({ me: ME });
    mockFetchJson({ body: { ok: true } });
    await useSession.getState().logout();
    expect(useSession.getState().me).toBeNull();
    expect(crossed).toHaveBeenCalledOnce();
  });
});
