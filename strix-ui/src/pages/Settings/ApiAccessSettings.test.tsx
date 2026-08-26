import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import ApiAccessSettings from "./ApiAccessSettings";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

const TOKEN = {
  id: "t1",
  name: "CI token",
  token_type: "personal",
  scopes: ["scans:read", "scans:write", "vulnerabilities:read"],
  token_prefix: "strix_abc12345",
  status: "active",
  last_used_at: null,
  expires_at: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString(),
  created_at: new Date().toISOString(),
};
const WEBHOOK = { id: "w1", url: "https://example.com/hook", events: ["pentest.completed"], secret: "shh", status: "active", created_at: new Date().toISOString() };

describe("ApiAccessSettings", () => {
  it("shows the tokens tab by default with an empty state", async () => {
    mockFetchImpl(async () => jsonRes([]));
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("No tokens found");
  });

  it("lists tokens with scopes/expiry and revokes one", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "DELETE") return jsonRes({ ok: true });
      if (url.includes("/tokens")) return jsonRes([TOKEN]);
      return jsonRes([]);
    });
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("CI token");
    expect(screen.getByText("scans:read")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
  });

  it("creates a new token with selected scopes and expiration, shown once", async () => {
    let created: Record<string, unknown> | null = null;
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.includes("/tokens")) {
        created = JSON.parse(init.body as string);
        return jsonRes({ ...TOKEN, token: "strix_abc123456789" });
      }
      if (url.includes("/tokens")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("No tokens found");

    await userEvent.click(screen.getByRole("button", { name: /New Token/ }));
    await screen.findByText("Create API Token");

    const submit = screen.getByRole("button", { name: "Create Token" });
    expect(submit).toBeDisabled(); // no scopes selected yet

    await userEvent.type(screen.getByPlaceholderText("CI remediation runner"), "My token");
    await userEvent.click(screen.getByText("scans:read"));
    expect(submit).not.toBeDisabled();

    await userEvent.selectOptions(screen.getByDisplayValue("Default (90 days)"), "30 days");
    await userEvent.click(submit);

    await screen.findByText("strix_abc123456789");
    expect(created).toMatchObject({ name: "My token", scopes: ["scans:read"], expires_in_days: 30 });
  });

  it("selecting 'No expiration' sends a null expires_in_days", async () => {
    let created: Record<string, unknown> | null = null;
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.includes("/tokens")) {
        created = JSON.parse(init.body as string);
        return jsonRes({ ...TOKEN, token: "strix_xyz" });
      }
      return jsonRes([]);
    });
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("No tokens found");
    await userEvent.click(screen.getByRole("button", { name: /New Token/ }));
    await userEvent.type(screen.getByPlaceholderText("CI remediation runner"), "Long lived");
    await userEvent.click(screen.getByText("audit:read"));
    await userEvent.selectOptions(screen.getByDisplayValue("Default (90 days)"), "No expiration");
    await userEvent.click(screen.getByRole("button", { name: "Create Token" }));
    await screen.findByText("strix_xyz");
    expect(created).toMatchObject({ expires_in_days: null });
  });

  it("switches to the webhooks tab, lists webhooks, and deletes one", async () => {
    mockFetchImpl(async (url, init) => {
      if (url.includes("/tokens")) return jsonRes([]);
      if (init?.method === "DELETE") return jsonRes({ ok: true });
      if (url.includes("/webhooks")) return jsonRes([WEBHOOK]);
      return jsonRes([]);
    });
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("No tokens found");

    await userEvent.click(screen.getByText("webhooks"));
    await screen.findByText("https://example.com/hook");
    expect(screen.getByText("pentest.completed")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
  });

  it("creates a webhook by selecting specific events", async () => {
    let created: Record<string, unknown> | null = null;
    mockFetchImpl(async (url, init) => {
      if (url.includes("/tokens")) return jsonRes([]);
      if (init?.method === "POST" && url.includes("/webhooks")) {
        created = JSON.parse(init.body as string);
        return jsonRes({ ...WEBHOOK, id: "w2", secret: "whsec_once" });
      }
      if (url.includes("/webhooks")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("No tokens found");
    await userEvent.click(screen.getByText("webhooks"));
    await screen.findByText("No webhooks configured");

    await userEvent.click(screen.getByRole("button", { name: /New Webhook/ }));
    const submit = screen.getByRole("button", { name: "Create Webhook" });
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByPlaceholderText("https://automations.example.com/strix-webhook"), "https://other.example.com/hook");
    await userEvent.click(screen.getByText("Pentest completed"));
    await userEvent.click(screen.getByText("Issue created"));
    expect(submit).not.toBeDisabled();
    await userEvent.click(submit);

    await screen.findByText("whsec_once");
    expect(created).toMatchObject({ url: "https://other.example.com/hook", events: ["pentest.completed", "issue.created"] });
  });

  it("selecting 'All events' clears other selections, and picking another event clears 'All events'", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/tokens")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("No tokens found");
    await userEvent.click(screen.getByText("webhooks"));
    await userEvent.click(screen.getByRole("button", { name: /New Webhook/ }));
    await userEvent.type(screen.getByPlaceholderText("https://automations.example.com/strix-webhook"), "https://other.example.com/hook");

    await userEvent.click(screen.getByText("Pentest completed"));
    await userEvent.click(screen.getByText("All events"));
    // Selecting "All events" should have deselected "Pentest completed" — check
    // by re-clicking "All events" (toggle off) and confirming the submit
    // button still requires a selection.
    await userEvent.click(screen.getByText("All events"));
    expect(screen.getByRole("button", { name: "Create Webhook" })).toBeDisabled();

    await userEvent.click(screen.getByText("All events"));
    await userEvent.click(screen.getByText("Pentest completed"));
    expect(screen.getByRole("button", { name: "Create Webhook" })).not.toBeDisabled();
  });

  it("deselecting a scope and switching token type work", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/tokens")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("No tokens found");
    await userEvent.click(screen.getByRole("button", { name: /New Token/ }));

    await userEvent.selectOptions(screen.getByDisplayValue("Personal token"), "Service token");
    await userEvent.click(screen.getByText("scans:read"));
    await userEvent.click(screen.getByText("scans:write"));
    const submit = screen.getByRole("button", { name: "Create Token" });
    expect(submit).not.toBeDisabled();

    // Deselect both — button should go back to disabled.
    await userEvent.click(screen.getByText("scans:read"));
    await userEvent.click(screen.getByText("scans:write"));
    expect(submit).toBeDisabled();
  });

  it("deselecting a webhook event returns to the disabled state", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/tokens")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<ApiAccessSettings />);
    await screen.findByText("No tokens found");
    await userEvent.click(screen.getByText("webhooks"));
    await userEvent.click(screen.getByRole("button", { name: /New Webhook/ }));
    await userEvent.type(screen.getByPlaceholderText("https://automations.example.com/strix-webhook"), "https://other.example.com/hook");

    await userEvent.click(screen.getByText("Pentest completed"));
    const submit = screen.getByRole("button", { name: "Create Webhook" });
    expect(submit).not.toBeDisabled();

    await userEvent.click(screen.getByText("Pentest completed"));
    expect(submit).toBeDisabled();
  });
});
