import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import BillingSettings from "./BillingSettings";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

describe("BillingSettings", () => {
  it("shows the trialing plan with an Add card button", async () => {
    mockFetchImpl(async () => jsonRes({ plan: "pro_trial", status: "trialing", trial_ends_at: "2026-02-01T00:00:00Z", card_added: false, current_period_end: null }));
    renderWithProviders(<BillingSettings />);
    await screen.findByText("pro trial");
    expect(screen.getByRole("button", { name: "Add card" })).toBeInTheDocument();
    expect(screen.getByText(/Trial ends/)).toBeInTheDocument();
    expect(screen.getByText("No invoices yet.")).toBeInTheDocument();
  });

  it("hides the Add card button once a card is on file", async () => {
    mockFetchImpl(async () => jsonRes({ plan: "pro", status: "active", trial_ends_at: null, card_added: true, current_period_end: null }));
    renderWithProviders(<BillingSettings />);
    await screen.findByText("pro");
    expect(screen.queryByRole("button", { name: "Add card" })).not.toBeInTheDocument();
  });

  it("adds a card", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST") return jsonRes({ plan: "pro_trial", status: "active", trial_ends_at: null, card_added: true, current_period_end: null });
      return jsonRes({ plan: "pro_trial", status: "trialing", trial_ends_at: null, card_added: false, current_period_end: null });
    });
    renderWithProviders(<BillingSettings />);
    const addCard = await screen.findByRole("button", { name: "Add card" });
    await userEvent.click(addCard);
    await screen.findByText("active");
  });
});
