import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import AuditLogsSettings from "./AuditLogsSettings";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

describe("AuditLogsSettings", () => {
  it("shows an empty state when there's no activity", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/api/members")) return jsonResponse([]);
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 50 });
    });
    renderWithProviders(<AuditLogsSettings />);
    await screen.findByText("No activity yet");
  });

  it("renders audit log entries", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/api/members")) return jsonResponse([]);
      return jsonResponse({
        items: [
          {
            id: "e1",
            actor_user_id: "u1",
            actor_email: "a@example.com",
            action: "org.renamed",
            target: "Acme",
            extra: {},
            created_at: new Date().toISOString(),
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      });
    });
    renderWithProviders(<AuditLogsSettings />);
    await screen.findByText("a@example.com");
    expect(screen.getByText("org renamed")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });

  it("switches to the Request Log tab and renders entries", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/api/members")) return jsonResponse([]);
      if (url.includes("/api/settings/request-logs")) {
        return jsonResponse({
          items: [
            {
              id: "r1",
              actor_email: "a@example.com",
              method: "PATCH",
              path: "/api/orgs/current",
              status_code: 200,
              duration_ms: 12,
              created_at: new Date().toISOString(),
            },
            {
              id: "r2",
              actor_email: "a@example.com",
              method: "HEAD",
              path: "/api/pentests/does-not-exist",
              status_code: 404,
              duration_ms: 3,
              created_at: new Date().toISOString(),
            },
          ],
          total: 2,
          page: 1,
          page_size: 50,
        });
      }
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 50 });
    });
    renderWithProviders(<AuditLogsSettings />);
    await userEvent.click(screen.getByText("Request Log"));
    await screen.findByText("/api/orgs/current");
    expect(screen.getByText("PATCH")).toBeInTheDocument();
    expect(screen.getByText("HEAD")).toBeInTheDocument();
    expect(screen.getByText("404")).toBeInTheDocument();
  });

  it("shows an empty state on the Request Log tab", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/api/members")) return jsonResponse([]);
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 50 });
    });
    renderWithProviders(<AuditLogsSettings />);
    await userEvent.click(screen.getByText("Request Log"));
    await screen.findByText("No request activity yet");
  });

  it("filters the audit log by actor and action", async () => {
    const fetchMock = mockFetchImpl(async (url) => {
      if (url.includes("/api/members")) {
        return jsonResponse([{ id: "m1", org_id: "o1", role: "admin", user: { id: "u1", email: "a@example.com", name: "A", two_factor_enabled: false } }]);
      }
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 50 });
    });
    renderWithProviders(<AuditLogsSettings />);
    await screen.findByText("No activity yet");

    await userEvent.click(screen.getByRole("button", { name: "Filter by actor" }));
    await userEvent.click(screen.getByRole("option", { name: "a@example.com" }));

    await userEvent.type(screen.getByPlaceholderText("Filter by action..."), "renamed");

    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("actor_user_id=u1"))).toBe(true);
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("action=renamed"))).toBe(true);
    });
  });

  it("filters the request log by method and status", async () => {
    const fetchMock = mockFetchImpl(async (url) => {
      if (url.includes("/api/members")) return jsonResponse([]);
      return jsonResponse({ items: [], total: 0, page: 1, page_size: 50 });
    });
    renderWithProviders(<AuditLogsSettings />);
    await userEvent.click(screen.getByText("Request Log"));
    await screen.findByText("No request activity yet");

    await userEvent.click(screen.getByRole("button", { name: "Filter by method" }));
    await userEvent.click(screen.getByRole("option", { name: "PATCH" }));

    await userEvent.click(screen.getByRole("button", { name: "Filter by status" }));
    await userEvent.click(screen.getByRole("option", { name: "4xx / 5xx (errors)" }));

    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("method=PATCH"))).toBe(true);
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("min_status=400"))).toBe(true);
    });
  });

  it("paginates through audit log results", async () => {
    const fetchMock = mockFetchImpl(async (url) => {
      if (url.includes("/api/members")) return jsonResponse([]);
      const page = url.includes("page=2") ? 2 : 1;
      return jsonResponse({
        items: [
          {
            id: `e${page}`,
            actor_user_id: "u1",
            actor_email: "a@example.com",
            action: "org.renamed",
            target: `page-${page}`,
            extra: {},
            created_at: new Date().toISOString(),
          },
        ],
        total: 120,
        page,
        page_size: 50,
      });
    });
    renderWithProviders(<AuditLogsSettings />);
    await screen.findByText("page-1");

    await userEvent.click(screen.getByRole("button", { name: "Next page" }));

    await vi.waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("page=2"))).toBe(true);
    });
  });
});
