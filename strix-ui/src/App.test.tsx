import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { useSession } from "./store/session";
import { mockFetchJson } from "./test/mock-fetch";

function renderApp(initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  useSession.setState({ me: null, loading: false, loaded: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("refreshes the session on mount", async () => {
    const fetchMock = mockFetchJson({ status: 401, body: { detail: "not_authenticated" } });
    renderApp("/login");
    await screen.findByText("Sign in to Strix");
    expect(fetchMock).toHaveBeenCalled();
  });

  it("redirects an unauthenticated user hitting a protected route to /login", async () => {
    mockFetchJson({ status: 401, body: { detail: "not_authenticated" } });
    renderApp("/dashboard");
    await screen.findByText("Sign in to Strix");
  });

  it("redirects an unknown route to /dashboard, which itself redirects to /login when unauthenticated", async () => {
    mockFetchJson({ status: 401, body: { detail: "not_authenticated" } });
    renderApp("/some/unknown/route");
    await screen.findByText("Sign in to Strix");
  });
});
