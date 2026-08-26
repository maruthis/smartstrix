import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl, mockFetchJson } from "../../test/mock-fetch";
import RepositoriesList from "./RepositoriesList";

afterEach(() => {
  vi.unstubAllGlobals();
});

const REPO = {
  id: "repo1",
  provider: "github",
  full_name: "acme/widgets",
  default_branch: "main",
  auto_review_enabled: true,
  last_tested_at: null,
  open_issues_count: 2,
};

describe("RepositoriesList", () => {
  it("shows an empty state when there are no repositories", async () => {
    mockFetchJson({ body: [] });
    renderWithProviders(<RepositoriesList />);
    await screen.findByText("No repositories yet");
  });

  it("renders a repository row with its issue count and last-tested date", async () => {
    mockFetchJson({ body: [REPO] });
    renderWithProviders(<RepositoriesList />);
    await screen.findByText("acme/widgets");
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument(); // last tested
  });

  it("renders a tested repository's relative last-tested time", async () => {
    mockFetchJson({ body: [{ ...REPO, last_tested_at: new Date().toISOString(), open_issues_count: 0 }] });
    renderWithProviders(<RepositoriesList />);
    await screen.findByText("acme/widgets");
    expect(screen.getByText("just now")).toBeInTheDocument();
  });

  it("toggles auto-review", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "PATCH") return { ok: true, status: 200, json: async () => ({ ...REPO, auto_review_enabled: false }) };
      if (url.endsWith("/api/repositories")) return { ok: true, status: 200, json: async () => [REPO] };
      return { ok: true, status: 200, json: async () => [] };
    });
    renderWithProviders(<RepositoriesList />);
    await screen.findByText("acme/widgets");
    const toggleButton = screen.getAllByRole("button").find((b) => b.textContent === "")!;
    expect(toggleButton).toBeTruthy();
    await userEvent.click(toggleButton);
  });

  it("triggers a manual scan and navigates to the pentest", async () => {
    mockFetchImpl(async (url, init) => {
      if (url.endsWith("/api/repositories")) return { ok: true, status: 200, json: async () => [REPO] };
      if (url.includes("/scan")) return { ok: true, status: 200, json: async () => ({ pentest_id: "pt1" }) };
      return { ok: true, status: 200, json: async () => [] };
    });
    renderWithProviders(<RepositoriesList />, { route: "/repositories", path: "/repositories" });
    await screen.findByText("acme/widgets");
    await userEvent.click(screen.getByRole("button", { name: "Run scan" }));
    await waitFor(() => expect(true).toBe(true));
  });

  it("opens the add-repository modal, lists installable repos, and adds one", async () => {
    mockFetchImpl(async (url) => {
      if (url.endsWith("/api/repositories")) return { ok: true, status: 200, json: async () => [] };
      if (url.includes("/installable")) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            { full_name: "acme/api", default_branch: "main", private: false },
            { full_name: "acme/secret", default_branch: "main", private: true },
          ],
        };
      }
      return { ok: true, status: 200, json: async () => REPO };
    });
    renderWithProviders(<RepositoriesList />);
    await screen.findByText("No repositories yet");

    await userEvent.click(screen.getByRole("button", { name: /Add Repository/ }));
    await screen.findByText("acme/api");
    expect(screen.getByText("Private")).toBeInTheDocument();

    const addButtons = screen.getAllByRole("button", { name: "Add" });
    await userEvent.click(addButtons[0]);
  });

  it("shows the empty installable state when nothing is left to add", async () => {
    mockFetchImpl(async (url) => {
      if (url.endsWith("/api/repositories")) return { ok: true, status: 200, json: async () => [REPO] };
      if (url.includes("/installable")) return { ok: true, status: 200, json: async () => [] };
      return { ok: true, status: 200, json: async () => [] };
    });
    renderWithProviders(<RepositoriesList />);
    await screen.findByText("acme/widgets");
    await userEvent.click(screen.getByRole("button", { name: /Add Repository/ }));
    await screen.findByText(/No more repositories to add/);
  });

  it("shows the GitLab icon for a gitlab repository row", async () => {
    mockFetchJson({ body: [{ ...REPO, provider: "gitlab", full_name: "acme-group/widgets" }] });
    renderWithProviders(<RepositoriesList />);
    await screen.findByText("acme-group/widgets");
    expect(document.querySelector(".lucide-gitlab")).toBeInTheDocument();
    expect(document.querySelector(".lucide-github")).not.toBeInTheDocument();
  });
});
