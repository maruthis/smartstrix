import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import IssueDetail from "./IssueDetail";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

const ISSUE = {
  id: "i1",
  org_id: "o1",
  pentest_id: "pt1",
  pr_review_id: null,
  repository_id: "r1",
  domain_id: null,
  title: "SQL injection in search",
  description: "Unsanitized input reaches a query.",
  severity: "critical",
  status: "open",
  cvss: 9.1,
  cvss_breakdown: {},
  technical_analysis: "The query builder concatenates raw input.",
  remediation_steps: "Use parameterized queries.",
  poc_description: "Send ' OR 1=1 -- in the search field.",
  poc_script_code: "",
  code_before: null,
  code_after: null,
  target: "acme/widgets",
  endpoint: "/search",
  fix_effort: "low",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

describe("IssueDetail", () => {
  it("shows a loading state before the issue loads", () => {
    mockFetchImpl(async () => new Promise(() => {}));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows an error when the issue cannot be loaded", async () => {
    mockFetchImpl(async () => ({ ok: false, status: 404, statusText: "Not Found", json: async () => ({ detail: "not_found" }) }));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText(/Couldn't load this page/);
  });

  it("renders issue fields including CVSS and endpoint", async () => {
    mockFetchImpl(async () => jsonRes(ISSUE));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    expect(screen.getByText("CVSS 9.1")).toBeInTheDocument();
    expect(screen.getByText("Unsanitized input reaches a query.")).toBeInTheDocument();
    expect(screen.getByText("The query builder concatenates raw input.")).toBeInTheDocument();
    expect(screen.getByText("Use parameterized queries.")).toBeInTheDocument();
    expect(screen.getByText("Fix effort: low")).toBeInTheDocument();
  });

  it("omits CVSS and endpoint when absent", async () => {
    mockFetchImpl(async () => jsonRes({ ...ISSUE, cvss: null, endpoint: "" }));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    expect(screen.queryByText(/CVSS/)).not.toBeInTheDocument();
  });

  it("omits a section entirely when its content is empty", async () => {
    mockFetchImpl(async () => jsonRes({ ...ISSUE, poc_description: "" }));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    expect(screen.queryByText("Proof of concept")).not.toBeInTheDocument();
  });

  it("changes status via the select", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "PATCH") return jsonRes({ ...ISSUE, status: "fixed" });
      return jsonRes(ISSUE);
    });
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    await userEvent.selectOptions(screen.getByDisplayValue("Open"), "Fixed");
  });

  it("navigates back when the back button is clicked", async () => {
    mockFetchImpl(async () => jsonRes(ISSUE));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    await userEvent.click(screen.getByRole("button", { name: /Back/ }));
  });

  it("shows an Automatically detected badge for a baseline-scan finding", async () => {
    mockFetchImpl(async () => jsonRes({ ...ISSUE, source: "baseline_scan" }));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    expect(screen.getByText("Automatically detected")).toBeInTheDocument();
  });

  it("shows a Mock fallback badge for a finding filed during a real-scan fallback", async () => {
    mockFetchImpl(async () => jsonRes({ ...ISSUE, source: "mock_fallback" }));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    expect(screen.getByText("Mock fallback")).toBeInTheDocument();
  });

  it("shows a Demo scanner badge for mock findings", async () => {
    mockFetchImpl(async () => jsonRes({ ...ISSUE, source: "mock" }));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    expect(screen.getAllByText("Demo scanner").length).toBeGreaterThan(0);
  });

  it("queues a retest and navigates to the new pentest", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && String(url).includes("/retest")) {
        return jsonRes({ id: "pt-retest", status: "queued", target_label: "acme/widgets" });
      }
      return jsonRes(ISSUE);
    });
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    await userEvent.click(screen.getByRole("button", { name: /Retest this finding/ }));
    await screen.findByTestId("test-route-fallback");
  });

  it("omits scanner badges for an agent-validated finding", async () => {
    mockFetchImpl(async () => jsonRes({ ...ISSUE, source: null }));
    renderWithProviders(<IssueDetail />, { route: "/issues/i1", path: "/issues/:id" });
    await screen.findByText("SQL injection in search");
    expect(screen.queryByText("Automatically detected")).not.toBeInTheDocument();
    expect(screen.queryByText("Demo scanner")).not.toBeInTheDocument();
  });
});
