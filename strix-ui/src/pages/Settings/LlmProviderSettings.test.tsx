import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import LlmProviderSettings from "./LlmProviderSettings";
import { useSession } from "../../store/session";

function jsonRes(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

const UNSET = { model: "", api_base: null, api_key_set: false, api_key_last4: null, updated_at: new Date().toISOString() };
const CONFIGURED = { model: "openai/gpt-5.4", api_base: "https://gateway.example.com/v1", api_key_set: true, api_key_last4: "1234", updated_at: new Date().toISOString() };

const ADMIN_ME = {
  user: { id: "u1", email: "a@example.com", name: "Ada", two_factor_enabled: false },
  active_org: { id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" },
  role: "admin",
  organizations: [],
};

beforeEach(() => {
  useSession.setState({ me: ADMIN_ME, loading: false, loaded: true });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LlmProviderSettings", () => {
  it("renders nothing before settings load", () => {
    mockFetchImpl(async () => new Promise(() => {}));
    const { container } = renderWithProviders(<LlmProviderSettings />);
    expect(container.textContent).toBe("");
  });

  it("shows an unconfigured state with no key hint", async () => {
    mockFetchImpl(async () => jsonRes(UNSET));
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByText("LLM Provider");
    expect(screen.getByText("No key saved yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });

  it("shows the masked key hint and a Clear button when configured", async () => {
    mockFetchImpl(async () => jsonRes(CONFIGURED));
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByDisplayValue("openai/gpt-5.4");
    expect(screen.getByText(/ending in •••1234/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
  });

  it("saves model/base/key changes", async () => {
    let sent: Record<string, unknown> | null = null;
    mockFetchImpl(async (url, init) => {
      if (init?.method === "PATCH") {
        sent = JSON.parse(init.body as string);
        return jsonRes({ ...UNSET, model: "openai/gpt-5.4" });
      }
      return jsonRes(UNSET);
    });
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByPlaceholderText("openai/gpt-5.4");

    await userEvent.type(screen.getByPlaceholderText("openai/gpt-5.4"), "openai/gpt-5.4");
    await userEvent.type(screen.getByPlaceholderText("https://api.openai.com/v1"), "https://gateway.example.com/v1");
    await userEvent.type(screen.getByPlaceholderText("sk-..."), "sk-new-key");
    await userEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(sent).toMatchObject({
      model: "openai/gpt-5.4",
      api_base: "https://gateway.example.com/v1",
      api_key: "sk-new-key",
    });
  });

  it("saves model/base changes without touching an already-set key", async () => {
    let sent: Record<string, unknown> | null = null;
    mockFetchImpl(async (url, init) => {
      if (init?.method === "PATCH") {
        sent = JSON.parse(init.body as string);
        return jsonRes({ ...CONFIGURED, model: "openai/gpt-5-mini" });
      }
      return jsonRes(CONFIGURED);
    });
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByDisplayValue("openai/gpt-5.4");

    const modelInput = screen.getByDisplayValue("openai/gpt-5.4");
    await userEvent.clear(modelInput);
    await userEvent.type(modelInput, "openai/gpt-5-mini");
    await userEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    expect(sent).not.toHaveProperty("api_key");
    expect(sent).toMatchObject({ model: "openai/gpt-5-mini" });
  });

  it("clears the saved key", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "PATCH") return jsonRes(UNSET);
      return jsonRes(CONFIGURED);
    });
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByRole("button", { name: "Clear" });
    await userEvent.click(screen.getByRole("button", { name: "Clear" }));
    await screen.findByText("No key saved yet.");
  });

  it("disables fields and hides Save/Clear for non-admins", async () => {
    useSession.setState({ me: { ...ADMIN_ME, role: "member" }, loading: false, loaded: true });
    mockFetchImpl(async () => jsonRes(CONFIGURED));
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByDisplayValue("openai/gpt-5.4");
    expect(screen.getByDisplayValue("openai/gpt-5.4")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save Changes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });
});
