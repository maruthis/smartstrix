import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/render";
import { mockFetchJson } from "../test/mock-fetch";
import { Sidebar } from "./Sidebar";
import { useSession } from "../store/session";

const ME = {
  user: { id: "u1", email: "a@example.com", name: "Ada", two_factor_enabled: false },
  active_org: { id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" },
  role: "admin",
  organizations: [
    { id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" },
    { id: "org2", name: "Beta", created_at: "2026-01-01T00:00:00Z" },
  ],
};

beforeEach(() => {
  useSession.setState({ me: ME, loading: false, loaded: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Sidebar", () => {
  it("shows the active org name and user footer", () => {
    renderWithProviders(<Sidebar />);
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("Ada")).toBeInTheDocument();
    expect(screen.getByText("a@example.com")).toBeInTheDocument();
  });

  it("renders every nav item, locking Networks", () => {
    renderWithProviders(<Sidebar />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Networks")).toBeInTheDocument();
    expect(screen.getByText("Integrations")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Integrations/ })).toBeInTheDocument();
  });

  it("does not render the removed Supply Chain nav item or Refer & earn button", () => {
    renderWithProviders(<Sidebar />);
    expect(screen.queryByText("Supply Chain")).not.toBeInTheDocument();
    expect(screen.queryByText(/Refer & earn/)).not.toBeInTheDocument();
  });

  it("opens the org switcher and switches org on click", async () => {
    mockFetchJson({ body: { ...ME, active_org: ME.organizations[1] } });
    renderWithProviders(<Sidebar />);

    await userEvent.click(screen.getByText("Acme"));
    expect(screen.getByText("Beta")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Beta"));
    expect(useSession.getState().me?.active_org?.id).toBe("org2");
  });

  it("logs out when the footer user block is clicked", async () => {
    mockFetchJson({ body: { ok: true } });
    renderWithProviders(<Sidebar />);
    await userEvent.click(screen.getByText("Ada"));
    expect(useSession.getState().me).toBeNull();
  });

  it("renders gracefully with no active session", () => {
    useSession.setState({ me: null, loading: false, loaded: true });
    renderWithProviders(<Sidebar />);
    expect(screen.getByText("Select org")).toBeInTheDocument();
  });
});
