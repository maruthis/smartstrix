import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { mockFetchImpl, mockFetchJson } from "../../test/mock-fetch";
import Login from "./Login";
import { useSession } from "../../store/session";

beforeEach(() => {
  useSession.setState({ me: null, loading: false, loaded: false });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Login", () => {
  it("submits an email and advances to the code step, showing the dev code", async () => {
    mockFetchJson({ body: { ok: true, dev_code: "123456" } });
    renderWithProviders(<Login />);

    await userEvent.type(screen.getByPlaceholderText("you@company.com"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue with email" }));

    await screen.findByText(/Enter the 6-digit code/);
    expect(screen.getByText("123456")).toBeInTheDocument();
  });

  it("shows an error message if starting the OTP fails", async () => {
    mockFetchJson({ status: 429, body: { detail: "rate_limited" } });
    renderWithProviders(<Login />);

    await userEvent.type(screen.getByPlaceholderText("you@company.com"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue with email" }));

    await screen.findByText("rate_limited");
  });

  it("verifies the code and navigates to /dashboard when the user has an org", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("otp/start")) return { ok: true, status: 200, json: async () => ({ ok: true, dev_code: "111111" }) };
      return {
        ok: true,
        status: 200,
        json: async () => ({
          user: { id: "u1", email: "a@example.com", name: "A", two_factor_enabled: false },
          active_org: { id: "org1", name: "Acme", created_at: "2026-01-01T00:00:00Z" },
          role: "admin",
          organizations: [],
        }),
      };
    });
    renderWithProviders(<Login />);

    await userEvent.type(screen.getByPlaceholderText("you@company.com"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue with email" }));
    await screen.findByPlaceholderText("123456");

    await userEvent.type(screen.getByPlaceholderText("123456"), "111111");
    await userEvent.click(screen.getByRole("button", { name: "Verify & continue" }));

    await waitFor(() => expect(useSession.getState().me?.active_org?.id).toBe("org1"));
  });

  it("verifying with no active org still succeeds (caller decides where to go)", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("otp/start")) return { ok: true, status: 200, json: async () => ({ ok: true }) };
      return {
        ok: true,
        status: 200,
        json: async () => ({
          user: { id: "u1", email: "a@example.com", name: "A", two_factor_enabled: false },
          active_org: null,
          role: null,
          organizations: [],
        }),
      };
    });
    renderWithProviders(<Login />);

    await userEvent.type(screen.getByPlaceholderText("you@company.com"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue with email" }));
    await screen.findByPlaceholderText("123456");
    // No dev code in the response, so the dev-mode hint shouldn't render.
    expect(screen.queryByText(/Dev mode/)).not.toBeInTheDocument();

    await userEvent.type(screen.getByPlaceholderText("123456"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify & continue" }));

    await waitFor(() => expect(useSession.getState().me).not.toBeNull());
  });

  it("shows an error message when verification fails", async () => {
    mockFetchImpl(async (url) => {
      if (url.includes("otp/start")) return { ok: true, status: 200, json: async () => ({ ok: true, dev_code: "111111" }) };
      return { ok: false, status: 403, json: async () => ({ detail: "invalid_or_expired_code" }) };
    });
    renderWithProviders(<Login />);

    await userEvent.type(screen.getByPlaceholderText("you@company.com"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue with email" }));
    await screen.findByPlaceholderText("123456");

    await userEvent.type(screen.getByPlaceholderText("123456"), "000000");
    await userEvent.click(screen.getByRole("button", { name: "Verify & continue" }));

    await screen.findByText("invalid_or_expired_code");
  });

  it("falls back to a generic error when starting the OTP throws a non-Error value", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw "network down"; // eslint-disable-line no-throw-literal
      })
    );
    renderWithProviders(<Login />);
    await userEvent.type(screen.getByPlaceholderText("you@company.com"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue with email" }));
    await screen.findByText("Something went wrong");
  });

  it("falls back to a generic error when verifying throws a non-Error value", async () => {
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        if (calls === 1) return { ok: true, status: 200, json: async () => ({ ok: true, dev_code: "111111" }) };
        throw "network down"; // eslint-disable-line no-throw-literal
      })
    );
    renderWithProviders(<Login />);
    await userEvent.type(screen.getByPlaceholderText("you@company.com"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue with email" }));
    await screen.findByPlaceholderText("123456");
    await userEvent.type(screen.getByPlaceholderText("123456"), "111111");
    await userEvent.click(screen.getByRole("button", { name: "Verify & continue" }));
    await screen.findByText("Invalid code");
  });

  it("lets the user go back to the email step", async () => {
    mockFetchJson({ body: { ok: true, dev_code: "111111" } });
    renderWithProviders(<Login />);

    await userEvent.type(screen.getByPlaceholderText("you@company.com"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Continue with email" }));
    await screen.findByPlaceholderText("123456");

    await userEvent.click(screen.getByText("Use a different email"));
    expect(screen.getByPlaceholderText("you@company.com")).toBeInTheDocument();
  });
});
