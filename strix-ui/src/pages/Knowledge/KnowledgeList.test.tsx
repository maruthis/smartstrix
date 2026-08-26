import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { delay, mockFetchImpl } from "../../test/mock-fetch";
import KnowledgeList from "./KnowledgeList";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

const ENTRY = {
  id: "k1",
  type: "business_logic",
  description: "Withdrawals are capped at $10k/day.",
  scope_type: "global",
  scope_id: null,
  created_at: new Date().toISOString(),
};

const REPO = { id: "r1", provider: "github", full_name: "acme/widgets", default_branch: "main", auto_review_enabled: true, last_tested_at: null, open_issues_count: 0 };
const DOMAIN = { id: "d1", hostname: "app.example.com", verified: true, verification_method: "dns_txt", verification_token: "x", last_tested_at: null };

describe("KnowledgeList", () => {
  it("shows an empty state", async () => {
    mockFetchImpl(async () => jsonRes([]));
    renderWithProviders(<KnowledgeList />);
    await screen.findByText("No custom context added");
  });

  it("renders an entry and deletes it", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "DELETE") return jsonRes({ ok: true });
      if (url.includes("/api/knowledge")) return jsonRes([ENTRY]);
      return jsonRes([]);
    });
    renderWithProviders(<KnowledgeList />);
    await screen.findByText(/Withdrawals are capped/);
    await userEvent.click(screen.getByRole("button", { name: "" }));
  });

  it("filters by search", async () => {
    mockFetchImpl(async () => jsonRes([ENTRY]));
    renderWithProviders(<KnowledgeList />);
    await screen.findByText(/Withdrawals are capped/);
    await userEvent.type(screen.getByPlaceholderText("Search knowledge"), "cap");
  });

  it("adds a global knowledge entry", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST") return jsonRes(ENTRY);
      if (url.includes("/api/knowledge")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<KnowledgeList />);
    await screen.findByText("No custom context added");

    await userEvent.click(screen.getByRole("button", { name: /Add Knowledge/ }));
    const submitButtons = screen.getAllByRole("button", { name: "Add Knowledge" });
    const submit = submitButtons[submitButtons.length - 1];
    expect(submit).toBeDisabled();

    await userEvent.type(screen.getByPlaceholderText(/Describe the business logic/), "Rate limit is 100/min.");
    expect(submit).not.toBeDisabled();
    await userEvent.click(submit);
  });

  it("switches scope to repository and selects a target", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST") return jsonRes(ENTRY);
      if (url.endsWith("/api/repositories")) return jsonRes([REPO]);
      if (url.endsWith("/api/domains")) return jsonRes([]);
      if (url.includes("/api/knowledge")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<KnowledgeList />);
    await screen.findByText("No custom context added");
    await userEvent.click(screen.getByRole("button", { name: /Add Knowledge/ }));

    await userEvent.selectOptions(screen.getByDisplayValue("Applies globally"), "Specific repository");
    await screen.findByText("acme/widgets");
    await userEvent.type(screen.getByPlaceholderText(/Describe the business logic/), "Repo-scoped note");
    const submitButtons = screen.getAllByRole("button", { name: "Add Knowledge" });
    expect(submitButtons[submitButtons.length - 1]).toBeDisabled();
    await userEvent.selectOptions(screen.getByDisplayValue("Select…"), "acme/widgets");
    expect(submitButtons[submitButtons.length - 1]).not.toBeDisabled();
    await userEvent.click(submitButtons[submitButtons.length - 1]);
  });

  it("switches scope to domain", async () => {
    mockFetchImpl(async (url) => {
      if (url.endsWith("/api/repositories")) return jsonRes([]);
      if (url.endsWith("/api/domains")) return jsonRes([DOMAIN]);
      if (url.includes("/api/knowledge")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<KnowledgeList />);
    await screen.findByText("No custom context added");
    await userEvent.click(screen.getByRole("button", { name: /Add Knowledge/ }));

    await userEvent.selectOptions(screen.getByDisplayValue("Applies globally"), "Specific domain");
    await screen.findByText("app.example.com");
  });

  it("shows a pending label while adding", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST") return delay({ ok: true, status: 200, json: async () => ENTRY });
      if (url.includes("/api/knowledge")) return jsonRes([]);
      return jsonRes([]);
    });
    renderWithProviders(<KnowledgeList />);
    await screen.findByText("No custom context added");
    await userEvent.click(screen.getByRole("button", { name: /Add Knowledge/ }));
    await userEvent.type(screen.getByPlaceholderText(/Describe the business logic/), "Note");
    const submitButtons = screen.getAllByRole("button", { name: "Add Knowledge" });
    await userEvent.click(submitButtons[submitButtons.length - 1]);
    await screen.findByText("Adding…");
  });
});
