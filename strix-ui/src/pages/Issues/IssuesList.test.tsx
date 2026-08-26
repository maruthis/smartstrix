import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import IssuesList from "./IssuesList";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

function makeIssue(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    id: "i1",
    org_id: "o1",
    pentest_id: null,
    pr_review_id: null,
    repository_id: "r1",
    domain_id: null,
    title: "SQL injection",
    description: "",
    severity: "critical",
    status: "open",
    cvss: null,
    cvss_breakdown: {},
    technical_analysis: "",
    remediation_steps: "",
    poc_description: "",
    poc_script_code: "",
    code_before: null,
    code_after: null,
    target: "acme/widgets",
    endpoint: "",
    fix_effort: "low",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

const RESPONSE = {
  items: [makeIssue()],
  severity_counts: { critical: 1, high: 0, medium: 0, low: 0 },
  status_counts: { all: 1, open: 1, in_progress: 0, snoozed: 0, fixed: 0, ignored: 0 },
};

const REPO = { id: "r1", provider: "github", full_name: "acme/widgets", default_branch: "main", auto_review_enabled: true, last_tested_at: null, open_issues_count: 1 };
const PENTEST = {
  id: "p1",
  org_id: "o1",
  target_type: "repository",
  target_id: "r1",
  target_label: "acme/widgets",
  scan_mode: "deep",
  status: "completed",
  started_at: new Date().toISOString(),
  finished_at: new Date().toISOString(),
  severity_counts: { critical: 1 },
  created_at: new Date().toISOString(),
};

function mockIssuesEnv(issuesResponse: unknown) {
  return mockFetchImpl(async (url) => {
    if (url.startsWith("/api/issues")) return jsonRes(issuesResponse);
    if (url.startsWith("/api/repositories")) return jsonRes([REPO]);
    if (url.startsWith("/api/pentests")) return jsonRes([PENTEST]);
    return jsonRes([]);
  });
}

describe("IssuesList", () => {
  it("shows an empty state when there are no issues", async () => {
    mockIssuesEnv({ items: [], severity_counts: { critical: 0, high: 0, medium: 0, low: 0 }, status_counts: { all: 0 } });
    renderWithProviders(<IssuesList />);
    await screen.findByText("No issues");
  });

  it("renders the severity summary, tabs, and issue rows", async () => {
    mockIssuesEnv(RESPONSE);
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Open/ })).toBeInTheDocument();
  });

  it("filters issues client-side by search text", async () => {
    mockIssuesEnv(RESPONSE);
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");
    await userEvent.type(screen.getByPlaceholderText("Search issues..."), "nonexistent");
    expect(screen.queryByText("SQL injection")).not.toBeInTheDocument();
  });

  it("switches status tabs", async () => {
    mockIssuesEnv(RESPONSE);
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");
    await userEvent.click(screen.getByText("Fixed"));
  });

  it("switches to board view and groups issues by status", async () => {
    mockIssuesEnv({
      items: [makeIssue({ id: "i1", status: "open" }), makeIssue({ id: "i2", status: "fixed", title: "XSS" })],
      severity_counts: { critical: 2, high: 0, medium: 0, low: 0 },
      status_counts: { all: 2, open: 1, fixed: 1 },
    });
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");

    await userEvent.click(screen.getByText("Board"));
    await screen.findByText("XSS");
    // Tabs (button-rendered) are hidden in board mode, though "Fixed" still
    // appears as a Board column label (a <span>, not a <button>).
    expect(screen.queryByRole("button", { name: "Fixed" })).not.toBeInTheDocument();
  });

  it("shows nothing in board mode when there are no issues at all", async () => {
    mockIssuesEnv({ items: [], severity_counts: { critical: 0, high: 0, medium: 0, low: 0 }, status_counts: { all: 0 } });
    renderWithProviders(<IssuesList />);
    await screen.findByText("No issues");
    await userEvent.click(screen.getByText("Board"));
  });

  it("populates the repository and pentest filter dropdowns", async () => {
    mockIssuesEnv(RESPONSE);
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");

    await userEvent.click(screen.getByRole("button", { name: "Filter by repository" }));
    expect(screen.getByRole("option", { name: "All Repositories" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "acme/widgets" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Filter by pentest" }));
    expect(screen.getByRole("option", { name: "All Pentests" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /p1 · acme\/widgets ·/ })).toBeInTheDocument();
  });

  it("refetches issues scoped to the selected repository", async () => {
    const fetchMock = mockIssuesEnv(RESPONSE);
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");

    await userEvent.click(screen.getByRole("button", { name: "Filter by repository" }));
    await userEvent.click(screen.getByRole("option", { name: "acme/widgets" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("repository_id=r1"))).toBe(true);
    });
  });

  it("shows an Automatically detected badge for a baseline-scan finding", async () => {
    mockIssuesEnv({
      items: [makeIssue({ source: "baseline_scan" })],
      severity_counts: { critical: 1, high: 0, medium: 0, low: 0 },
      status_counts: { all: 1, open: 1 },
    });
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");
    expect(screen.getByText("Automatically detected")).toBeInTheDocument();
  });

  it("shows a Mock fallback badge for a finding filed during a real-scan fallback", async () => {
    mockIssuesEnv({
      items: [makeIssue({ source: "mock_fallback" })],
      severity_counts: { critical: 1, high: 0, medium: 0, low: 0 },
      status_counts: { all: 1, open: 1 },
    });
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");
    expect(screen.getByText("Mock fallback")).toBeInTheDocument();
  });

  it("omits the badge for an agent-validated finding", async () => {
    mockIssuesEnv(RESPONSE);
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");
    expect(screen.queryByText("Automatically detected")).not.toBeInTheDocument();
  });

  it("refetches issues scoped to the selected pentest", async () => {
    const fetchMock = mockIssuesEnv(RESPONSE);
    renderWithProviders(<IssuesList />);
    await screen.findByText("SQL injection");

    await userEvent.click(screen.getByRole("button", { name: "Filter by pentest" }));
    await userEvent.click(screen.getByRole("option", { name: /p1 · acme\/widgets ·/ }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("pentest_id=p1"))).toBe(true);
    });
  });
});
