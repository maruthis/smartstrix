import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl, mockFetchJson } from "../../test/mock-fetch";
import GeneralSettings from "./GeneralSettings";
import { useSession } from "../../store/session";
import { act } from "@testing-library/react";

const ADMIN_ME = {
  user: { id: "u1", email: "a@example.com", name: "Ada", two_factor_enabled: false },
  active_org: { id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" },
  role: "admin",
  organizations: [{ id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" }],
};

const MEMBER_ME = { ...ADMIN_ME, role: "member" };

beforeEach(() => {
  useSession.setState({ me: ADMIN_ME, loading: false, loaded: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("GeneralSettings", () => {
  it("renders nothing without an active org", () => {
    useSession.setState({ me: null, loading: false, loaded: true });
    const { container } = renderWithProviders(<GeneralSettings />);
    expect(container.firstChild).toBeNull();
  });

  it("renders profile info and org details for an admin, including the danger zone", () => {
    renderWithProviders(<GeneralSettings />);
    expect(screen.getByText("Ada")).toBeInTheDocument();
    expect(screen.getByText("a@example.com")).toBeInTheDocument();
    expect(screen.getByText("Danger Zone")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Acme")).not.toBeDisabled();
  });

  it("syncs the rename field when the active organization changes", () => {
    renderWithProviders(<GeneralSettings />);
    expect(screen.getByDisplayValue("Acme")).toBeInTheDocument();
    act(() => {
      useSession.setState({
        me: {
          ...ADMIN_ME,
          active_org: { id: "org2", name: "Beta", created_at: "2026-01-01T00:00:00Z" },
          organizations: [
            ...ADMIN_ME.organizations,
            { id: "org2", name: "Beta", created_at: "2026-01-01T00:00:00Z" },
          ],
        },
      });
    });
    expect(screen.getByDisplayValue("Beta")).toBeInTheDocument();
  });

  it("hides the danger zone and disables the name field for non-admins", () => {
    useSession.setState({ me: MEMBER_ME, loading: false, loaded: true });
    renderWithProviders(<GeneralSettings />);
    expect(screen.queryByText("Danger Zone")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue("Acme")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeDisabled();
  });

  it("renames the organization", async () => {
    mockFetchJson({ body: { ok: true } });
    renderWithProviders(<GeneralSettings />);
    const nameInput = screen.getByDisplayValue("Acme");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "New Name");
    await userEvent.click(screen.getByRole("button", { name: "Save Changes" }));
  });

  it("requires the exact org name before enabling delete, then deletes", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "DELETE") return { ok: true, status: 200, json: async () => ({ ok: true }) };
      // refresh() -> GET /api/auth/me
      return { ok: true, status: 200, json: async () => ({ ...ADMIN_ME, active_org: null, role: null, organizations: [] }) };
    });
    renderWithProviders(<GeneralSettings />);
    const confirmInput = screen.getByPlaceholderText('Type "Acme" to confirm');
    const deleteButton = screen.getByRole("button", { name: "Delete Organization" });
    expect(deleteButton).toBeDisabled();

    await userEvent.type(confirmInput, "wrong");
    expect(deleteButton).toBeDisabled();

    await userEvent.clear(confirmInput);
    await userEvent.type(confirmInput, "Acme");
    expect(deleteButton).not.toBeDisabled();
    await userEvent.click(deleteButton);
  });

  it("signs out", async () => {
    mockFetchJson({ body: { ok: true } });
    renderWithProviders(<GeneralSettings />);
    await userEvent.click(screen.getByRole("button", { name: "Sign Out" }));
  });
});
