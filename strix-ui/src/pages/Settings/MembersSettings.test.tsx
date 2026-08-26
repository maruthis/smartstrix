import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import MembersSettings from "./MembersSettings";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

const MEMBER = { id: "m1", org_id: "o1", role: "admin", user: { id: "u1", email: "a@example.com", name: "Ada", two_factor_enabled: false } };
const INVITATION = { id: "inv1", email: "new@example.com", role: "member", created_at: new Date().toISOString() };

describe("MembersSettings", () => {
  it("renders team members and an empty invitations state", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/invitations")) return jsonRes([]);
      return jsonRes([MEMBER]);
    });
    renderWithProviders(<MembersSettings />);
    await screen.findByText("Ada");
    expect(screen.getByText("Team Members (1)")).toBeInTheDocument();
    expect(screen.getByText("No pending invitations")).toBeInTheDocument();
  });

  it("renders pending invitations and revokes one", async () => {
    mockFetchImpl(async (url, init) => {
      if (url.includes("/revoke")) return jsonRes({ ok: true });
      if (url.includes("/invitations")) return jsonRes([INVITATION]);
      return jsonRes([MEMBER]);
    });
    renderWithProviders(<MembersSettings />);
    await screen.findByText("new@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Revoke" }));
  });

  it("opens the invite modal and sends an invitation", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.includes("/invitations")) return jsonRes({ dev_accept_token: "tok" });
      if (url.includes("/invitations")) return jsonRes([]);
      return jsonRes([MEMBER]);
    });
    renderWithProviders(<MembersSettings />);
    await screen.findByText("Ada");

    await userEvent.click(screen.getByRole("button", { name: /Invite Member/ }));
    await userEvent.type(screen.getByPlaceholderText("teammate@company.com"), "new@example.com");
    await userEvent.selectOptions(screen.getByDisplayValue("Member"), "Admin");
    await userEvent.click(screen.getByRole("button", { name: "Send Invitation" }));
  });
});
