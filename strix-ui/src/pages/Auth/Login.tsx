import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type { MeOut } from "../../api/types";
import { useSession } from "../../store/session";
import { Button, TextInput } from "../../components/shared/Form";

export default function Login() {
  const navigate = useNavigate();
  const setMe = useSession((s) => s.setMe);
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function startOtp(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ ok: boolean; dev_code?: string }>("/api/auth/otp/start", { email });
      setDevCode(res.dev_code ?? null);
      setStep("code");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function verifyOtp(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = await api.post<MeOut>("/api/auth/otp/verify", { email, code });
      setMe(me);
      navigate(me.active_org ? "/dashboard" : "/onboarding");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid code");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-black px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-white text-lg font-bold text-black">
            S
          </div>
          <h1 className="text-lg font-semibold text-white">Sign in to Strix</h1>
        </div>

        {step === "email" ? (
          <form onSubmit={startOtp} className="space-y-3">
            <TextInput
              type="email"
              required
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoFocus
            />
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Sending…" : "Continue with email"}
            </Button>
          </form>
        ) : (
          <form onSubmit={verifyOtp} className="space-y-3">
            <p className="text-center text-sm text-[#888]">
              Enter the 6-digit code sent to <span className="text-white">{email}</span>
            </p>
            {devCode && (
              <p className="rounded-lg border border-[#2a2a2a] bg-[rgba(255,255,255,0.03)] px-3 py-2 text-center text-xs text-[#888]">
                Dev mode — no email provider configured yet (see <code>saas/CONFIG.md</code>). Your code:{" "}
                <span className="font-mono text-white">{devCode}</span>
              </p>
            )}
            <TextInput
              required
              inputMode="numeric"
              maxLength={6}
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoFocus
              className="text-center text-lg tracking-[0.5em]"
            />
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Verifying…" : "Verify & continue"}
            </Button>
            <button
              type="button"
              onClick={() => setStep("email")}
              className="w-full text-center text-xs text-[#666] hover:text-white"
            >
              Use a different email
            </button>
          </form>
        )}

        {error && <p className="mt-3 text-center text-sm text-red-400">{error}</p>}
      </div>
    </div>
  );
}
