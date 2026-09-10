import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl } from "../../test/mock-fetch";
import LlmProviderSettings from "./LlmProviderSettings";
import { useSession } from "../../store/session";

function jsonRes(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, statusText: "error", json: async () => body };
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
    expect(screen.getByRole("button", { name: "Validate" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeEnabled();
  });

  it("shows the masked key hint and a Clear button when configured", async () => {
    mockFetchImpl(async () => jsonRes(CONFIGURED));
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByDisplayValue("openai/gpt-5.4");
    expect(screen.getByText(/ending in •••1234/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
  });

  it("accepts any model name without a trusted-prefix check", async () => {
    mockFetchImpl(async () => jsonRes(UNSET));
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByPlaceholderText("openai/gpt-5.4");
    await userEvent.type(screen.getByPlaceholderText("openai/gpt-5.4"), "accounts/fireworks/models/kimi-k2p6");
    expect(screen.queryByText(/trusted list/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeDisabled();
  });

  it("keeps Save disabled until Validate succeeds, then saves", async () => {
    let saved: Record<string, unknown> | null = null;
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && String(url).includes("/validate")) {
        return jsonRes({ ok: true, message: "Connection verified. You can save these settings." });
      }
      if (init?.method === "PATCH") {
        saved = JSON.parse(init.body as string);
        return jsonRes({ ...UNSET, model: "accounts/fireworks/models/kimi-k2p6" });
      }
      return jsonRes(UNSET);
    });
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByPlaceholderText("openai/gpt-5.4");

    await userEvent.type(screen.getByPlaceholderText("openai/gpt-5.4"), "accounts/fireworks/models/kimi-k2p6");
    await userEvent.type(screen.getByPlaceholderText("https://api.openai.com/v1"), "https://api.fireworks.ai/inference/v1");
    await userEvent.type(screen.getByPlaceholderText("sk-..."), "fw-new-key");

    expect(screen.getByRole("button", { name: "Save Changes" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByText("Connection verified. You can save these settings.");
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    expect(saved).toMatchObject({
      model: "accounts/fireworks/models/kimi-k2p6",
      api_base: "https://api.fireworks.ai/inference/v1",
      api_key: "fw-new-key",
    });
  });

  it("shows a business error when Validate fails and does not enable Save", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && String(url).includes("/validate")) {
        return jsonRes({ detail: "The API key was rejected. Check the key and try again." }, 400);
      }
      return jsonRes(UNSET);
    });
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByPlaceholderText("openai/gpt-5.4");
    await userEvent.type(screen.getByPlaceholderText("openai/gpt-5.4"), "openai/gpt-5.4");
    await userEvent.type(screen.getByPlaceholderText("sk-..."), "sk-bad");
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByText("The API key was rejected. Check the key and try again.");
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeDisabled();
  });

  it("requires re-validation after the model changes", async () => {
    mockFetchImpl(async (url, init) => {
      if (init?.method === "POST" && String(url).includes("/validate")) {
        return jsonRes({ ok: true, message: "Connection verified. You can save these settings." });
      }
      return jsonRes(UNSET);
    });
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByPlaceholderText("openai/gpt-5.4");
    await userEvent.type(screen.getByPlaceholderText("openai/gpt-5.4"), "openai/gpt-5.4");
    await userEvent.type(screen.getByPlaceholderText("sk-..."), "sk-new-key");
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    await screen.findByText("Connection verified. You can save these settings.");
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeEnabled();

    await userEvent.type(screen.getByPlaceholderText("openai/gpt-5.4"), "-mini");
    expect(screen.getByRole("button", { name: "Save Changes" })).toBeDisabled();
  });

  it("saves a blank model without validation so the org can use the server default", async () => {
    let saved: Record<string, unknown> | null = null;
    mockFetchImpl(async (_url, init) => {
      if (init?.method === "PATCH") {
        saved = JSON.parse(init.body as string);
        return jsonRes(UNSET);
      }
      return jsonRes(CONFIGURED);
    });
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByDisplayValue("openai/gpt-5.4");
    await userEvent.clear(screen.getByDisplayValue("openai/gpt-5.4"));
    await userEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    expect(saved).toMatchObject({ model: "" });
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

  it("disables fields and hides Save/Clear/Validate for non-admins", async () => {
    useSession.setState({ me: { ...ADMIN_ME, role: "member" }, loading: false, loaded: true });
    mockFetchImpl(async () => jsonRes(CONFIGURED));
    renderWithProviders(<LlmProviderSettings />);
    await screen.findByDisplayValue("openai/gpt-5.4");
    expect(screen.getByDisplayValue("openai/gpt-5.4")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save Changes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Validate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });
});
