import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "./AppShell";
import { useSession } from "../store/session";
import { mockFetchJson } from "../test/mock-fetch";

function renderShell(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route path="/onboarding" element={<div>Onboarding page</div>} />
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<div>Dashboard page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  useSession.setState({ me: null, loading: false, loaded: false });
  mockFetchJson({ status: 200, body: {} });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AppShell", () => {
  it("shows a loading state before the session has loaded", () => {
    renderShell("/dashboard");
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects to /login when there is no session", () => {
    useSession.setState({ me: null, loading: false, loaded: true });
    renderShell("/dashboard");
    expect(screen.getByText("Login page")).toBeInTheDocument();
  });

  it("redirects to /onboarding when the user has no active org", () => {
    useSession.setState({
      me: { user: { id: "u1", email: "a@example.com", name: "A", two_factor_enabled: false }, active_org: null, role: null, organizations: [] },
      loading: false,
      loaded: true,
    });
    renderShell("/dashboard");
    expect(screen.getByText("Onboarding page")).toBeInTheDocument();
  });

  it("renders the shell and nested route once authenticated with an org", () => {
    useSession.setState({
      me: {
        user: { id: "u1", email: "a@example.com", name: "A", two_factor_enabled: false },
        active_org: { id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" },
        role: "admin",
        organizations: [{ id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" }],
      },
      loading: false,
      loaded: true,
    });
    renderShell("/dashboard");
    expect(screen.getByText("Dashboard page")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
  });
});
