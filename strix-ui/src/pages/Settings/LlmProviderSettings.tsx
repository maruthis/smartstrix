import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { LlmSettings } from "../../api/types";
import { useSession } from "../../store/session";
import { Button, Field, TextInput } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";

const TRUSTED_MODEL_PREFIXES = ["openai/", "anthropic/", "azure/", "bedrock/", "vertex_ai/"];

function validateModel(model: string): string | null {
  if (!model.trim()) return null;
  if (!model.includes("/")) return "Use provider/model format so routing and audit logs are explicit.";
  if (!TRUSTED_MODEL_PREFIXES.some((prefix) => model.startsWith(prefix))) {
    return "This provider is not in the default trusted list. Add it server-side before routing scans there.";
  }
  return null;
}

function validateApiBase(apiBase: string): string | null {
  if (!apiBase.trim()) return null;
  try {
    const url = new URL(apiBase);
    if (url.protocol !== "https:" && url.hostname !== "localhost" && url.hostname !== "127.0.0.1") {
      return "Use HTTPS for provider or gateway URLs outside local development.";
    }
  } catch {
    return "Enter a valid absolute URL.";
  }
  return null;
}

export default function LlmProviderSettings() {
  const queryClient = useQueryClient();
  const isAdmin = useSession((s) => s.me?.role === "admin");

  const { data: settings } = useQuery({ queryKey: ["llm-settings"], queryFn: () => api.get<LlmSettings>("/api/settings/llm") });

  const [model, setModel] = useState<string | null>(null);
  const [apiBase, setApiBase] = useState<string | null>(null);
  const [apiKeyDraft, setApiKeyDraft] = useState("");

  const effectiveModel = model ?? settings?.model ?? "";
  const effectiveApiBase = apiBase ?? settings?.api_base ?? "";
  const modelError = validateModel(effectiveModel);
  const apiBaseError = validateApiBase(effectiveApiBase);
  const canSave = isAdmin && !modelError && !apiBaseError;

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
      toast.success("LLM settings saved");
    },
  });

  const clearKey = useMutation({
    mutationFn: () => api.patch<LlmSettings>("/api/settings/llm", { clear_api_key: true }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["llm-settings"], updated);
      toast.success("API key cleared");
    },
  });

  if (!settings) return null;

  return (
    <div className="max-w-2xl">
      <h1 className="mb-1 text-xl font-semibold text-white">LLM Provider</h1>
      <p className="mb-6 text-sm text-[#888]">
        Configure which model backs this organization's pentests and PR reviews. Applied per-scan — overrides the
        server's default model/credentials for runs belonging to this org only.
      </p>

      <div className="space-y-4 rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-5">
        <Field label="Model" hint='litellm-style "provider/model", e.g. "openai/gpt-5.4" or "anthropic/claude-sonnet-4-6"'>
          <TextInput
            placeholder="openai/gpt-5.4"
            value={effectiveModel}
            onChange={(e) => setModel(e.target.value)}
            disabled={!isAdmin}
          />
          {modelError && <div className="mt-1 text-xs text-red-300">{modelError}</div>}
        </Field>

        <Field label="API Base URL" hint="Optional — set to point at a self-hosted or gateway endpoint">
          <TextInput
            placeholder="https://api.openai.com/v1"
            value={effectiveApiBase}
            onChange={(e) => setApiBase(e.target.value)}
            disabled={!isAdmin}
          />
          {apiBaseError && <div className="mt-1 text-xs text-red-300">{apiBaseError}</div>}
        </Field>

        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs leading-relaxed text-amber-100">
          Model routing controls where repository code, prompts, findings, and remediation context may be sent. Keep
          custom gateways on an approved allowlist and verify retention, training, and audit terms before enabling real scans.
        </div>

        <Field
          label="API Key"
          hint={settings.api_key_set ? `A key ending in •••${settings.api_key_last4} is saved. Enter a new one to replace it.` : "No key saved yet."}
        >
          <div className="flex gap-2">
            <TextInput
              type="password"
              placeholder={settings.api_key_set ? "•••••••••••••••• (unchanged)" : "sk-..."}
              value={apiKeyDraft}
              onChange={(e) => setApiKeyDraft(e.target.value)}
              disabled={!isAdmin}
            />
            {settings.api_key_set && isAdmin && (
              <Button variant="secondary" onClick={() => clearKey.mutate()} disabled={clearKey.isPending}>
                Clear
              </Button>
            )}
          </div>
        </Field>

        {isAdmin && (
          <Button onClick={() => save.mutate()} disabled={!canSave || save.isPending}>
            {save.isPending ? "Saving…" : "Save Changes"}
          </Button>
        )}
      </div>

      <p className="mt-4 text-xs text-[#555]">
        Leave Model blank to fall back to this server's process-wide default (set by whoever deployed it). Real
        pentest execution against this configuration must be enabled by the operator — see <code>saas/CONFIG.md</code>.
      </p>
    </div>
  );
}
