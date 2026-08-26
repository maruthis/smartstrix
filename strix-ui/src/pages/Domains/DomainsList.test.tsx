import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { delay, mockFetchImpl, mockFetchJson } from "../../test/mock-fetch";
import DomainsList from "./DomainsList";

afterEach(() => {
  vi.unstubAllGlobals();
});

const UNVERIFIED = {
  id: "d1",
  hostname: "app.example.com",
  verified: false,
  verification_method: "dns_txt",
  verification_token: "strix-verify=abc",
  last_tested_at: null,
};

describe("DomainsList", () => {
  it("shows an empty state when there are no domains", async () => {
    mockFetchJson({ body: [] });
    renderWithProviders(<DomainsList />);
    await screen.findByText("No domains");
  });

  it("renders an unverified domain with a Verify button", async () => {
    mockFetchJson({ body: [UNVERIFIED] });
    renderWithProviders(<DomainsList />);
    await screen.findByText("app.example.com");
    expect(screen.getByText("Unverified")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Verify/ })).toBeInTheDocument();
  });

  it("renders a verified domain with a Run scan button", async () => {
    mockFetchJson({ body: [{ ...UNVERIFIED, verified: true, last_tested_at: new Date().toISOString() }] });
    renderWithProviders(<DomainsList />);
    await screen.findByText("app.example.com");
    expect(screen.getByRole("button", { name: "Run scan" })).toBeInTheDocument();
    expect(screen.getByText("just now", { exact: false })).toBeInTheDocument();
  });

  it("verifies a domain without navigating away", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.includes("/verify")) return { ok: true, status: 200, json: async () => ({ ...UNVERIFIED, verified: true }) };
      if (url.endsWith("/api/domains")) return { ok: true, status: 200, json: async () => [UNVERIFIED] };
      return { ok: true, status: 200, json: async () => [] };
    });
    renderWithProviders(<DomainsList />);
    await screen.findByText("app.example.com");
    await userEvent.click(screen.getByRole("button", { name: /Verify/ }));
  });

  it("adds a new domain via the modal", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.endsWith("/api/domains")) return { ok: true, status: 200, json: async () => ({ ...UNVERIFIED, hostname: "new.example.com" }) };
      if (url.endsWith("/api/domains")) return { ok: true, status: 200, json: async () => [] };
      return { ok: true, status: 200, json: async () => [] };
    });
    renderWithProviders(<DomainsList />);
    await screen.findByText("No domains");

    await userEvent.click(screen.getByRole("button", { name: /Add Domain/ }));
    await userEvent.type(screen.getByPlaceholderText("app.example.com"), "new.example.com");
    const addButtons = screen.getAllByRole("button", { name: "Add Domain" });
    await userEvent.click(addButtons[addButtons.length - 1]);
  });

  it("shows a pending label on the submit button while adding", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.endsWith("/api/domains")) return delay({ ok: true, status: 200, json: async () => UNVERIFIED });
      return { ok: true, status: 200, json: async () => [] };
    });
    renderWithProviders(<DomainsList />);
    await screen.findByText("No domains");
    await userEvent.click(screen.getByRole("button", { name: /Add Domain/ }));
    await userEvent.type(screen.getByPlaceholderText("app.example.com"), "new.example.com");
    const addButtons = screen.getAllByRole("button", { name: "Add Domain" });
    await userEvent.click(addButtons[addButtons.length - 1]);
    await screen.findByText("Adding…");
  });

  it("strips scheme and path when adding a pasted URL", async () => {
    let posted: unknown;
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.endsWith("/api/domains")) {
        posted = JSON.parse(String(init.body));
        return { ok: true, status: 200, json: async () => ({ ...UNVERIFIED, hostname: "dev-stag-agui.techsophy.com" }) };
      }
      if (url.endsWith("/api/domains")) return { ok: true, status: 200, json: async () => [] };
      return { ok: true, status: 200, json: async () => [] };
    });
    renderWithProviders(<DomainsList />);
    await screen.findByText("No domains");

    await userEvent.click(screen.getByRole("button", { name: /Add Domain/ }));
    await userEvent.type(screen.getByPlaceholderText("app.example.com"), "https://dev-stag-agui.techsophy.com/");
    const addButtons = screen.getAllByRole("button", { name: "Add Domain" });
    await userEvent.click(addButtons[addButtons.length - 1]);
    await waitFor(() => expect(posted).toEqual({ hostname: "dev-stag-agui.techsophy.com" }));
  });
});
