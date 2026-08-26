import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import DomainDetail from "./DomainDetail";

afterEach(() => {
  vi.unstubAllGlobals();
});

const UNVERIFIED = {
  id: "d1",
  hostname: "app.example.com",
  verified: false,
  verification_method: "dns_txt",
  verification_token: "strix-verify=abc",
  last_tested_at: null,
};

const VERIFIED = { ...UNVERIFIED, verified: true, last_tested_at: new Date().toISOString() };

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

describe("DomainDetail", () => {
  it("shows a loading state before the domain loads", () => {
    mockFetchImpl(async () => new Promise(() => {})); // never resolves
    renderWithProviders(<DomainDetail />, { route: "/domains/d1", path: "/domains/:id" });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows verification instructions for an unverified domain", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/api/domains/d1") && !url.includes("verify") && !url.includes("scan")) return jsonRes(UNVERIFIED);
      if (url.includes("/api/pentests")) return jsonRes([]);
      if (url.includes("/api/issues")) return jsonRes({ items: [] });
      return jsonRes({});
    });
    renderWithProviders(<DomainDetail />, { route: "/domains/d1", path: "/domains/:id" });
    await screen.findByText("app.example.com");
    expect(screen.getByText("Verify ownership")).toBeInTheDocument();
    expect(screen.getByText("strix-verify=abc")).toBeInTheDocument();
    expect(screen.getByText("Never tested")).toBeInTheDocument();
    await screen.findByText("No scans yet.");
  });

  it("shows file-based verification instructions when that method is used", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("/api/domains/d1") && !url.includes("verify") && !url.includes("scan")) return jsonRes({ ...UNVERIFIED, verification_method: "file" });
      if (url.includes("/api/pentests")) return jsonRes([]);
      if (url.includes("/api/issues")) return jsonRes({ items: [] });
      return jsonRes({});
    });
    renderWithProviders(<DomainDetail />, { route: "/domains/d1", path: "/domains/:id" });
    await screen.findByText("Verify ownership");
    expect(screen.getByText(/as a file for/)).toBeInTheDocument();
  });

  it("shows the scan action, scan history, and findings for a verified domain", async () => {
    const pentest = { id: "pt1", org_id: "o1", target_type: "domain", target_id: "d1", target_label: "app.example.com", scan_mode: "deep", status: "completed", started_at: null, finished_at: null, severity_counts: {}, created_at: new Date().toISOString() };
    const issue = { id: "i1", org_id: "o1", pentest_id: "pt1", pr_review_id: null, repository_id: null, domain_id: "d1", title: "XSS found", description: "", severity: "high", status: "open", cvss: null, cvss_breakdown: {}, technical_analysis: "", remediation_steps: "", poc_description: "", poc_script_code: "", code_before: null, code_after: null, target: "", endpoint: "", fix_effort: "low", created_at: new Date().toISOString(), updated_at: new Date().toISOString() };

    mockFetchImpl(async (url) => {
      if (url.includes("/api/pentests")) return jsonRes([pentest]);
      if (url.includes("/api/issues")) return jsonRes({ items: [issue] });
      if (url.includes("/api/domains/d1")) return jsonRes(VERIFIED);
      return jsonRes({});
    });
    renderWithProviders(<DomainDetail />, { route: "/domains/d1", path: "/domains/:id" });
    await screen.findByText("app.example.com");
    expect(screen.getByRole("button", { name: "Run scan" })).toBeInTheDocument();
    await screen.findByText("deep scan");
    await screen.findByText("XSS found");
  });

  it("verifies the domain via the button", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.includes("verify")) return jsonRes(VERIFIED);
      if (url.includes("/api/pentests")) return jsonRes([]);
      if (url.includes("/api/issues")) return jsonRes({ items: [] });
      if (url.includes("/api/domains/d1")) return jsonRes(UNVERIFIED);
      return jsonRes({});
    });
    renderWithProviders(<DomainDetail />, { route: "/domains/d1", path: "/domains/:id" });
    await screen.findByText("Verify ownership");
    await userEvent.click(screen.getByRole("button", { name: /verify now/ }));
    await screen.findByRole("button", { name: "Run scan" });
  });

  it("removes the domain after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mockFetchImpl(async (url, init) => {
      if (init?.method === "DELETE") return jsonRes({ ok: true });
      if (url.includes("/api/pentests")) return jsonRes([]);
      if (url.includes("/api/issues")) return jsonRes({ items: [] });
      if (url.includes("/api/domains/d1")) return jsonRes(UNVERIFIED);
      return jsonRes({});
    });
    renderWithProviders(<DomainDetail />, { route: "/domains/d1", path: "/domains/:id" });
    await screen.findByText("app.example.com");
    const buttons = screen.getAllByRole("button");
    const trashButton = buttons.find((b) => b.className.includes("hover:text-red-400"))!;
    await userEvent.click(trashButton);
  });
});
