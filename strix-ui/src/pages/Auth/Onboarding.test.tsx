import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import Onboarding from "./Onboarding";
import { useSession } from "../../store/session";

beforeEach(() => {
  useSession.setState({ me: null, loading: false, loaded: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Onboarding", () => {
  it("creates an org, switches to it, and refreshes the session", async () => {
    const calls: string[] = [];
    mockFetchImpl(async (url) => {
      calls.push(url);
      if (url.includes("/api/orgs")) return { ok: true, status: 200, json: async () => ({ id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" }) };
      if (url.includes("switch-org")) return { ok: true, status: 200, json: async () => ({}) };
      // /api/auth/me (from refresh)
      return {
        ok: true,
        status: 200,
        json: async () => ({
          user: { id: "u1", email: "a@example.com", name: "A", two_factor_enabled: false },
          active_org: { id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" },
          role: "admin",
          organizations: [],
        }),
      };
    });

    renderWithProviders(<Onboarding />);
    await userEvent.type(screen.getByPlaceholderText("Acme Inc"), "Acme");
    await userEvent.click(screen.getByRole("button", { name: "Create organization" }));

    await waitFor(() => expect(calls.some((c) => c.includes("switch-org"))).toBe(true));
    await waitFor(() => expect(useSession.getState().me?.active_org?.id).toBe("org1"));
  });

  it("shows an error when organization creation fails", async () => {
    mockFetchImpl(async () => ({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: async () => ({ detail: "name_required" }),
    }));
    renderWithProviders(<Onboarding />);
    await userEvent.type(screen.getByPlaceholderText("Acme Inc"), "Acme");
    await userEvent.click(screen.getByRole("button", { name: "Create organization" }));
    await screen.findByText("name_required");
  });
});
