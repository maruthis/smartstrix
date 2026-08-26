import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import PRReviewDetail from "./PRReviewDetail";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

const BASE_REVIEW = {
  id: "pr1",
  repository_id: "r1",
  repository_full_name: "acme/widgets",
  pr_number: 42,
  title: "Add withdraw endpoint",
  author: "octocat",
  findings_count: 0,
  target_branch: null,
  resolved_head_sha: null,
  error: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

function mockLogsAndIssuesEmpty(url: string) {
  if (url.includes("/logs")) return jsonRes({ available: false, lines: [], total_lines: 0, total_matched: 0, agent_ids: [] });
  if (url.includes("/issues")) return jsonRes([]);
  return null;
}

describe("PRReviewDetail", () => {
  it("shows a loading state before the review loads", () => {
    mockFetchImpl(async () => new Promise(() => {}));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows a scanning indicator with a progress bar while running", async () => {
    mockFetchImpl(async (url) => mockLogsAndIssuesEmpty(url) ?? jsonRes({ ...BASE_REVIEW, status: "running" }));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText(/Scanning this pull request's changes/);
    expect(screen.getByText(/running in the background/)).toBeInTheDocument();
  });

  it("shows elapsed time once running", async () => {
    mockFetchImpl(async (url) => mockLogsAndIssuesEmpty(url) ?? jsonRes({ ...BASE_REVIEW, status: "running" }));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText(/elapsed/);
  });

  it("shows no report links while running", async () => {
    mockFetchImpl(async (url) => mockLogsAndIssuesEmpty(url) ?? jsonRes({ ...BASE_REVIEW, status: "running" }));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText(/Scanning this pull request's changes/);
    expect(screen.queryByText("View report")).not.toBeInTheDocument();
  });

  it("shows the failure reason and no report link for a failed review", async () => {
    mockFetchImpl(async (url) => mockLogsAndIssuesEmpty(url) ?? jsonRes({ ...BASE_REVIEW, status: "failed", error: "scan_failed" }));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText(/This review failed: scan_failed/);
    expect(screen.queryByText("View report")).not.toBeInTheDocument();
  });

  it("shows the severity summary, findings, and report links once done", async () => {
    const issue = {
      id: "i1", org_id: "o1", pentest_id: null, pr_review_id: "pr1", repository_id: "r1", domain_id: null,
      title: "SQLi", description: "", severity: "critical", status: "open", cvss: null, cvss_breakdown: {},
      technical_analysis: "", remediation_steps: "", poc_description: "", poc_script_code: "", code_before: null,
      code_after: null, target: "", endpoint: "", fix_effort: "low", source: null,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    };
    mockFetchImpl(async (url) => {
      if (url.includes("/logs")) return jsonRes({ available: false, lines: [], total_lines: 0, total_matched: 0, agent_ids: [] });
      if (url.includes("/issues")) return jsonRes([issue]);
      return jsonRes({ ...BASE_REVIEW, status: "needs_attention", findings_count: 1, resolved_head_sha: "abc1234def5678" });
    });
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText("acme/widgets");
    await screen.findByText("SQLi");
    expect(screen.getByText("1")).toBeInTheDocument(); // critical count
    expect(screen.getByText("View report")).toHaveAttribute("href", "/api/pr-reviews/pr1/report");
    expect(screen.getByText("Download PDF")).toHaveAttribute("href", "/api/pr-reviews/pr1/report/download");
    expect(screen.getByText("abc1234def56")).toBeInTheDocument();
  });

  it("shows a no-findings message when done with zero issues", async () => {
    mockFetchImpl(async (url) => mockLogsAndIssuesEmpty(url) ?? jsonRes({ ...BASE_REVIEW, status: "passed" }));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText("No findings from this review.");
  });

  it("shows the target branch when present", async () => {
    mockFetchImpl(async (url) => mockLogsAndIssuesEmpty(url) ?? jsonRes({ ...BASE_REVIEW, status: "passed", target_branch: "main" }));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText("main");
  });

  it("navigates back to the PR reviews list", async () => {
    mockFetchImpl(async (url) => mockLogsAndIssuesEmpty(url) ?? jsonRes({ ...BASE_REVIEW, status: "running" }));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText(/Scanning this pull request's changes/);
    await userEvent.click(screen.getByRole("button", { name: /PR Reviews/ }));
  });
});

describe("PRReviewDetail run log", () => {
  it("shows a PR-review-specific empty state when no run log is available", async () => {
    mockFetchImpl(async (url) => mockLogsAndIssuesEmpty(url) ?? jsonRes({ ...BASE_REVIEW, status: "passed" }));
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText("No run log available");
    // Not the pentest-specific "used the mock scanner" copy — PR reviews
    // never use a mock scanner.
    expect(screen.getByText(/This PR review predates run-log capture/)).toBeInTheDocument();
  });

  it("renders log lines and filters by level", async () => {
    const lines = [
      { ts: "2026-08-19 16:11:51.190", level: "DEBUG", scan_id: "pr1", agent_id: "-", logger: "openai.agents", message: "Calling LLM" },
      { ts: "2026-08-19 16:11:56.274", level: "WARNING", scan_id: "pr1", agent_id: "abcd1234", logger: "strix.tools", message: "something odd" },
    ];
    mockFetchImpl(async (url) => {
      if (url.includes("/logs")) return jsonRes({ available: true, lines, total_lines: 2, total_matched: 2, agent_ids: ["abcd1234"] });
      if (url.includes("/issues")) return jsonRes([]);
      return jsonRes({ ...BASE_REVIEW, status: "passed" });
    });
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText("Calling LLM");
    expect(screen.getByText("something odd")).toBeInTheDocument();
    expect(screen.getByText("[abcd1234]")).toBeInTheDocument();
  });

  it("re-fetches logs with level/agent/query params once filters are set", async () => {
    const fetchMock = mockFetchImpl(async (url) => {
      if (url.includes("/logs")) {
        return jsonRes({
          available: true,
          total_lines: 1,
          total_matched: 1,
          agent_ids: ["agentA"],
          lines: [{ ts: "t1", level: "ERROR", scan_id: "pr1", agent_id: "agentA", logger: "x", message: "boom" }],
        });
      }
      if (url.includes("/issues")) return jsonRes([]);
      return jsonRes({ ...BASE_REVIEW, status: "passed" });
    });
    renderWithProviders(<PRReviewDetail />, { route: "/pr-reviews/pr1", path: "/pr-reviews/:id" });
    await screen.findByText("boom");

    await userEvent.click(screen.getByRole("button", { name: "Filter by level" }));
    await userEvent.click(screen.getByRole("option", { name: "Error" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes("level=ERROR"))).toBe(true);
    });
  });
});
