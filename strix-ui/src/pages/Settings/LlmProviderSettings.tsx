import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiErrorMessage } from "../../api/client";
import type { LlmSettings } from "../../api/types";
import { useSession } from "../../store/session";
import { Button, Field, TextInput } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";

function validateApiBase(apiBase: string): string | null {
  if (!apiBase.trim()) return null;
  try {
    new URL(apiBase);
  } catch {
    return "Enter a valid absolute URL.";
  }
  return null;
}

function draftFingerprint(model: string, apiBase: string, apiKeyDraft: string): string {
  return JSON.stringify({ model: model.trim(), apiBase: apiBase.trim(), apiKeyDraft });
}

export default function LlmProviderSettings() {
  const queryClient = useQueryClient();
  const isAdmin = useSession((s) => s.me?.role === "admin");

  const { data: settings } = useQuery({ queryKey: ["llm-settings"], queryFn: () => api.get<LlmSettings>("/api/settings/llm") });

  const [model, setModel] = useState<string | null>(null);
  const [apiBase, setApiBase] = useState<string | null>(null);
  const [apiKeyDraft, setApiKeyDraft] = useState("");
  const [validatedFor, setValidatedFor] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const effectiveModel = model ?? settings?.model ?? "";
  const effectiveApiBase = apiBase ?? settings?.api_base ?? "";
  const apiBaseError = validateApiBase(effectiveApiBase);
  const fingerprint = draftFingerprint(effectiveModel, effectiveApiBase, apiKeyDraft);
  const isVerified = validatedFor === fingerprint;
  const canSaveBlankOverride = isAdmin && !effectiveModel.trim() && !apiKeyDraft;
  const canSave = isAdmin && !apiBaseError && (isVerified || canSaveBlankOverride);

  const validate = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; message: string }>("/api/settings/llm/validate", {
        model: effectiveModel,
        api_base: effectiveApiBase,
        ...(apiKeyDraft ? { api_key: apiKeyDraft } : {}),
      }),
    onSuccess: (result) => {
      setValidatedFor(fingerprint);
      setStatusMessage({ type: "success", text: result.message });
      toast.success(result.message);
    },
    onError: (error) => {
      setValidatedFor(null);
      const text = apiErrorMessage(error, "We couldn't verify this provider. Try again.");
      setStatusMessage({ type: "error", text });
      toast.error(text);
    },
  });

  const save = useMutation({
    mutationFn: () =>
      api.patch<LlmSettings>("/api/settings/llm", {
        model: effectiveModel,
        api_base: effectiveApiBase,
        ...(apiKeyDraft ? { api_key: apiKeyDraft } : {}),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["llm-settings"], updated);
      setApiKeyDraft("");
      setValidatedFor(null);
      setStatusMessage(null);
      toast.success("LLM settings saved");
    },
    onError: (error) => {
      const text = apiErrorMessage(error, "We couldn't save these settings. Try again.");
      setStatusMessage({ type: "error", text });
      toast.error(text);
    },
  });

  const clearKey = useMutation({
    mutationFn: () => api.patch<LlmSettings>("/api/settings/llm", { clear_api_key: true }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["llm-settings"], updated);
      setApiKeyDraft("");
      setValidatedFor(null);
      toast.success("API key cleared");
    },
  });

  const markEdited = () => {
    setValidatedFor(null);
    setStatusMessage(null);
  };

  if (!settings) return null;

  return (
    <div className="max-w-2xl">
      <h1 className="mb-1 text-xl font-semibold text-white">LLM Provider</h1>
      <p className="mb-6 text-sm text-[#888]">
        Configure which model backs this organization's pentests and PR reviews. Applied per-scan — overrides the
        server's default model/credentials for runs belonging to this org only.
      </p>

      <div className="space-y-4 rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-5">
        <Field label="Model" hint='Any model id your provider accepts, e.g. "openai/gpt-5.4" or a gateway model name'>
          <TextInput
            placeholder="openai/gpt-5.4"
            value={effectiveModel}
            onChange={(e) => {
              setModel(e.target.value);
              markEdited();
            }}
            disabled={!isAdmin}
          />
        </Field>

        <Field label="API Base URL" hint="Optional — set to point at a self-hosted or gateway endpoint">
          <TextInput
            placeholder="https://api.openai.com/v1"
            value={effectiveApiBase}
            onChange={(e) => {
              setApiBase(e.target.value);
              markEdited();
            }}
            disabled={!isAdmin}
          />
          {apiBaseError && <div className="mt-1 text-xs text-red-300">{apiBaseError}</div>}
        </Field>

        <Field
          label="API Key"
          hint={settings.api_key_set ? `A key ending in •••${settings.api_key_last4} is saved. Enter a new one to replace it.` : "No key saved yet."}
        >
          <div className="flex gap-2">
            <TextInput
              type="password"
              placeholder={settings.api_key_set ? "•••••••••••••••• (unchanged)" : "sk-..."}
              value={apiKeyDraft}
              onChange={(e) => {
                setApiKeyDraft(e.target.value);
                markEdited();
              }}
              disabled={!isAdmin}
            />
            {settings.api_key_set && isAdmin && (
              <Button variant="secondary" onClick={() => clearKey.mutate()} disabled={clearKey.isPending}>
                Clear
              </Button>
            )}
          </div>
        </Field>

        {statusMessage && (
          <div
            className={
              statusMessage.type === "success"
                ? "rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs leading-relaxed text-emerald-100"
                : "rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs leading-relaxed text-red-200"
            }
          >
            {statusMessage.text}
          </div>
        )}

        {isAdmin && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() => validate.mutate()}
              disabled={!!apiBaseError || !effectiveModel.trim() || validate.isPending}
            >
              {validate.isPending ? "Checking…" : "Validate"}
            </Button>
            <Button onClick={() => save.mutate()} disabled={!canSave || save.isPending}>
              {save.isPending ? "Saving…" : "Save Changes"}
            </Button>
          </div>
        )}
      </div>

      <p className="mt-4 text-xs text-[#555]">
        Validate the connection before saving. Leave Model blank to fall back to this server's process-wide default.
        Real pentest execution against this configuration must be enabled by the operator — see <code>saas/CONFIG.md</code>.
      </p>
    </div>
  );
}
