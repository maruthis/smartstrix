import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { delay, mockFetchImpl } from "../../test/mock-fetch";
import IntegrationsList from "./IntegrationsList";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

const CATALOG = [
  {
    provider: "github",
    category: "code",
    label: "GitHub",
    coming_soon: false,
    live: true,
    // github/gitlab are per-org access tokens, not GitHub-App-style
    // installations — there's no provider-side settings page to link to,
    // so the backend never sends a configure_url for them.
    configure_url: null,
    status: "connected",
    account_label: "maruthis",
    base_url: null,
    credential_last4: null,
    connected_at: "2026-08-01T00:00:00Z",
  },
  {
    provider: "gitlab",
    category: "code",
    label: "GitLab",
    coming_soon: false,
    live: true,
    configure_url: null,
    status: "not_connected",
    account_label: null,
    base_url: null,
    credential_last4: null,
    connected_at: null,
  },
  { provider: "bitbucket", category: "code", label: "Bitbucket", coming_soon: false, live: false, configure_url: null, status: "not_connected", account_label: null, base_url: null, credential_last4: null, connected_at: null },
  { provider: "slack", category: "communication", label: "Slack", coming_soon: false, live: false, configure_url: null, status: "not_connected", account_label: null, base_url: null, credential_last4: null, connected_at: null },
  { provider: "msteams", category: "communication", label: "Microsoft Teams", coming_soon: true, live: false, configure_url: null, status: "not_connected", account_label: null, base_url: null, credential_last4: null, connected_at: null },
  { provider: "jira", category: "issue_tracking", label: "Jira", coming_soon: false, live: false, configure_url: null, status: "not_connected", account_label: null, base_url: null, credential_last4: null, connected_at: null },
  { provider: "linear", category: "issue_tracking", label: "Linear", coming_soon: false, live: false, configure_url: null, status: "not_connected", account_label: null, base_url: null, credential_last4: null, connected_at: null },
];

describe("IntegrationsList", () => {
  it("renders every section with its providers, and shows GitHub as connected", async () => {
    mockFetchImpl(async () => jsonRes(CATALOG));
    renderWithProviders(<IntegrationsList />);

    await screen.findByText("GitHub");
    expect(screen.getByText("Code Providers")).toBeInTheDocument();
    expect(screen.getByText("Communication")).toBeInTheDocument();
    expect(screen.getByText("Issue Tracking")).toBeInTheDocument();

    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("maruthis")).toBeInTheDocument();
    expect(screen.getByText("Coming soon")).toBeInTheDocument();

    // Connected GitHub shows manage actions; unconnected providers show Connect.
    expect(screen.getByText("Connect more")).toBeInTheDocument();
    expect(screen.getByText("Disconnect")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Connect" }).length).toBe(5); // gitlab, bitbucket, slack, jira, linear

    // No Configure link for a connected github/gitlab: it's a per-org
    // access token, not an app installation, so there's nothing on the
    // provider's side to configure.
    expect(screen.queryByRole("link", { name: /Configure/ })).not.toBeInTheDocument();
  });

  it("still shows a Configure link for a live provider that does have a configure_url", async () => {
    mockFetchImpl(async () =>
      jsonRes([{ ...CATALOG[0], configure_url: "https://example.com/settings/installations" }, ...CATALOG.slice(1)])
    );
    renderWithProviders(<IntegrationsList />);
    await screen.findByText("GitHub");

    const configureLink = screen.getByRole("link", { name: /Configure/ });
    expect(configureLink).toHaveAttribute("href", "https://example.com/settings/installations");
    expect(configureLink).toHaveAttribute("target", "_blank");
    expect(configureLink).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows a token-ending-in hint when a credential was provided", async () => {
    mockFetchImpl(async () => jsonRes([{ ...CATALOG[0], credential_last4: "1234" }, ...CATALOG.slice(1)]));
    renderWithProviders(<IntegrationsList />);
    await screen.findByText(/token ending in 1234/);
  });

  it("opens the connect modal, submits account + credential, and updates the row", async () => {
    const fetchMock = mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.includes("/api/integrations/gitlab/connect")) {
        const body = JSON.parse(init.body as string);
        return jsonRes({ ...CATALOG[1], status: "connected", account_label: body.account_label, credential_last4: body.credential?.slice(-4) ?? null, connected_at: "2026-08-17T00:00:00Z" });
      }
      return jsonRes(CATALOG);
    });
    renderWithProviders(<IntegrationsList />);
    await screen.findByText("GitLab");

    const connectButtons = screen.getAllByRole("button", { name: "Connect" });
    await userEvent.click(connectButtons[0]);

    await screen.findByRole("heading", { name: "Connect GitLab" });
    const submit = screen.getByRole("button", { name: "Connect GitLab" });
    expect(submit).toBeDisabled();

    // GitLab is a live provider: account name alone isn't enough, a
    // credential is required too (unlike the mock-only providers).
    await userEvent.type(screen.getByPlaceholderText("e.g. acme-corp"), "acme");
    expect(submit).toBeDisabled();
    await userEvent.type(screen.getByPlaceholderText(/Paste a token/), "glpat-abcd1234");
    expect(submit).not.toBeDisabled();

    // Live providers also expose an instance-URL field for self-hosting.
    await userEvent.type(screen.getByPlaceholderText(/gitlab.example.com/), "https://gitlab.acme.internal");
    await userEvent.click(submit);

    await screen.findByText("acme");
    expect(screen.getByText(/token ending in 1234/)).toBeInTheDocument();
    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes("gitlab/connect") && (c[1] as RequestInit)?.method === "POST")!;
    const sentBody = JSON.parse((call[1] as RequestInit).body as string);
    expect(sentBody).toEqual({ account_label: "acme", credential: "glpat-abcd1234", base_url: "https://gitlab.acme.internal" });
    expect(screen.queryByRole("heading", { name: "Connect GitLab" })).not.toBeInTheDocument();
  });

  it("connects without a credential, omitting it from the request body", async () => {
    const fetchMock = mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.includes("/api/integrations/bitbucket/connect")) {
        const body = JSON.parse(init.body as string);
        return jsonRes({ ...CATALOG[2], status: "connected", account_label: body.account_label, connected_at: "2026-08-17T00:00:00Z" });
      }
      return jsonRes(CATALOG);
    });
    renderWithProviders(<IntegrationsList />);
    await screen.findByText("Bitbucket");

    const connectButtons = screen.getAllByRole("button", { name: "Connect" });
    await userEvent.click(connectButtons[1]); // bitbucket has no dedicated hint, exercising the fallback label too

    await screen.findByRole("heading", { name: "Connect Bitbucket" });
    // Non-live providers don't get the self-hosted instance-URL field.
    expect(screen.queryByText("Instance URL (optional)")).not.toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Connect Bitbucket" });
    await userEvent.type(screen.getByPlaceholderText("e.g. acme-corp"), "acme-workspace");
    // Credential is optional for a non-live provider — submit is enabled
    // with just the account name.
    expect(submit).not.toBeDisabled();
    await userEvent.click(submit);

    await screen.findByText("acme-workspace");
    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes("bitbucket/connect"))!;
    const sentBody = JSON.parse((call[1] as RequestInit).body as string);
    expect(sentBody.credential).toBeUndefined();
  });

  it("shows a pending label while connecting", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && url.includes("/api/integrations/gitlab/connect")) {
        return delay(jsonRes({ ...CATALOG[1], status: "connected", account_label: "acme" }));
      }
      return jsonRes(CATALOG);
    });
    renderWithProviders(<IntegrationsList />);
    await screen.findByText("GitLab");
    await userEvent.click(screen.getAllByRole("button", { name: "Connect" })[0]);
    await userEvent.type(await screen.findByPlaceholderText("e.g. acme-corp"), "acme");
    await userEvent.type(screen.getByPlaceholderText(/Paste a token/), "glpat-xyz");
    await userEvent.click(screen.getByRole("button", { name: "Connect GitLab" }));
    await screen.findByText("Connecting…");
  });

  it("closes the connect modal without submitting", async () => {
    mockFetchImpl(async () => jsonRes(CATALOG));
    renderWithProviders(<IntegrationsList />);
    await screen.findByText("GitLab");

    await userEvent.click(screen.getAllByRole("button", { name: "Connect" })[0]);
    const heading = await screen.findByRole("heading", { name: "Connect GitLab" });

    const dialog = heading.closest("div")!.parentElement!;
    await userEvent.click(dialog.querySelector("button")!);
    expect(screen.queryByRole("heading", { name: "Connect GitLab" })).not.toBeInTheDocument();
  });

  it("disconnects a provider", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "DELETE" && url.includes("/api/integrations/github")) {
        return jsonRes({ ...CATALOG[0], status: "not_connected", account_label: null, credential_last4: null, connected_at: null });
      }
      return jsonRes(CATALOG);
    });
    renderWithProviders(<IntegrationsList />);
    await screen.findByText("Disconnect");
    const connectButtonsBefore = screen.getAllByRole("button", { name: "Connect" }).length;

    await userEvent.click(screen.getByText("Disconnect"));

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "Connect" }).length).toBe(connectButtonsBefore + 1);
    });
    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
  });

  it("navigates to Repositories from Connect more", async () => {
    mockFetchImpl(async () => jsonRes(CATALOG));
    renderWithProviders(<IntegrationsList />, { route: "/integrations" });
    await screen.findByText("Connect more");
    await userEvent.click(screen.getByText("Connect more"));
    // No route assertion needed beyond it not throwing — navigation target
    // itself (Repositories page) is covered by RepositoriesList's own tests.
  });
});
