import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Key, Plus, Webhook as WebhookIcon } from "lucide-react";
import { api } from "../../api/client";
import type { ApiToken, Webhook } from "../../api/types";
import { EmptyState } from "../../components/shared/EmptyState";
import { Modal } from "../../components/shared/Modal";
import { StatusPill } from "../../components/shared/StatusPill";
import { Button, Field, Select, TextInput } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";
import { cn } from "../../lib/cn";
import { formatDate, timeAgo } from "../../lib/format";

const SCOPE_GROUPS: { label: string; scopes: string[] }[] = [
  { label: "Scans", scopes: ["scans:read", "scans:write", "scans:message"] },
  { label: "Vulnerabilities", scopes: ["vulnerabilities:read", "vulnerabilities:write"] },
  { label: "Dependencies", scopes: ["dependencies:read", "dependency_issues:read", "dependency_issues:write"] },
  { label: "Supply chain", scopes: ["supply_chain:read", "supply_chain:write"] },
  { label: "Schedules", scopes: ["schedules:read", "schedules:write"] },
  { label: "Assets", scopes: ["assets:read", "assets:write"] },
  { label: "PR reviews", scopes: ["pr_reviews:read"] },
  { label: "Organization", scopes: ["organizations:read", "organizations:write", "members:read", "members:write"] },
  { label: "Invitations", scopes: ["invitations:read", "invitations:write"] },
  { label: "API access", scopes: ["tokens:write", "webhooks:read", "webhooks:write"] },
  { label: "Audit", scopes: ["audit:read"] },
];

const EXPIRATION_OPTIONS = [
  { value: "90", label: "Default (90 days)" },
  { value: "30", label: "30 days" },
  { value: "60", label: "60 days" },
  { value: "365", label: "1 year" },
  { value: "", label: "No expiration" },
];

const WEBHOOK_EVENTS: { key: string; label: string; description: string }[] = [
  { key: "pentest.completed", label: "Pentest completed", description: "A pentest finished successfully." },
  { key: "pentest.failed", label: "Pentest failed", description: "A pentest ended in a failed status." },
  { key: "issue.created", label: "Issue created", description: "A new issue was filed from a pentest or PR review." },
  { key: "pr_review.completed", label: "PR review completed", description: "A pull request review finished." },
  { key: "pr_review.failed", label: "PR review failed", description: "A pull request review ended in a failed status." },
  { key: "*", label: "All events", description: "Subscribes the endpoint to every current webhook event. The payload matches the event that fired." },
];

export default function ApiAccessSettings() {
  const [tab, setTab] = useState<"tokens" | "webhooks">("tokens");

  return (
    <div>
      <h1 className="text-xl font-semibold text-white">API Access</h1>
      <p className="mt-1 text-sm text-[#888]">Use the Strix API to programmatically run pentests, manage vulnerabilities, and receive webhooks.</p>

      <div className="my-5 inline-flex rounded-lg border border-[#2a2a2a] p-0.5">
        {(["tokens", "webhooks"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn("rounded-md px-3 py-1.5 text-sm capitalize", tab === t ? "bg-[rgba(255,255,255,0.1)] text-white" : "text-[#888]")}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "tokens" ? <TokensPanel /> : <WebhooksPanel />}
    </div>
  );
}

function TokensPanel() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [newToken, setNewToken] = useState<string | null>(null);

  const { data: tokens, isLoading } = useQuery({ queryKey: ["api-tokens"], queryFn: () => api.get<ApiToken[]>("/api/settings/tokens") });

  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/api/settings/tokens/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-tokens"] });
      toast.success("Token revoked");
    },
  });

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> New Token
        </Button>
      </div>

      {!isLoading && tokens?.length === 0 && <EmptyState icon={<Key size={20} />} title="No tokens found" />}

      {tokens && tokens.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-[#222]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#222] text-left text-xs uppercase tracking-wide text-[#666]">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Scopes</th>
                <th className="px-4 py-3 font-medium">Expires</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {tokens.map((t) => {
                const visibleScopes = t.scopes.slice(0, 2);
                const remaining = t.scopes.length - visibleScopes.length;
                return (
                  <tr key={t.id} className="border-b border-[#1a1a1a] last:border-0">
                    <td className="px-4 py-3">
                      <div className="text-white">{t.name}</div>
                      <div className="font-mono text-xs text-[#666]">{t.token_prefix}… · Created {timeAgo(t.created_at)}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {visibleScopes.map((s) => (
                          <span key={s} className="rounded-full border border-[#2a2a2a] px-2 py-0.5 text-[10px] text-[#aaa]">
                            {s}
                          </span>
                        ))}
                        {remaining > 0 && <span className="rounded-full border border-[#2a2a2a] px-2 py-0.5 text-[10px] text-[#aaa]">+{remaining}</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-[#888]">{t.expires_at ? formatDate(t.expires_at) : "Never"}</td>
                    <td className="px-4 py-3">
                      <StatusPill value={t.status} />
                    </td>
                    <td className="px-4 py-3">
                      {t.status === "active" && (
                        <Button variant="ghost" onClick={() => revoke.mutate(t.id)}>
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Create API Token" description="Create a token for headless automations." width="max-w-xl">
        <NewTokenForm
          onCreated={(token) => {
            setNewToken(token);
            setCreateOpen(false);
            queryClient.invalidateQueries({ queryKey: ["api-tokens"] });
          }}
        />
      </Modal>

      <Modal open={!!newToken} onClose={() => setNewToken(null)} title="Token created">
        <p className="mb-2 text-sm text-[#888]">Copy this token now — you won't be able to see it again.</p>
        <div className="break-all rounded-lg border border-[#2a2a2a] bg-black p-3 font-mono text-xs text-emerald-400">{newToken}</div>
      </Modal>
    </div>
  );
}

function NewTokenForm({ onCreated }: { onCreated: (token: string) => void }) {
  const [name, setName] = useState("");
  const [tokenType, setTokenType] = useState("personal");
  const [scopes, setScopes] = useState<string[]>([]);
  const [expiresInDays, setExpiresInDays] = useState("90");

  const create = useMutation({
    mutationFn: () =>
      api.post<ApiToken & { token: string }>("/api/settings/tokens", {
        name,
        token_type: tokenType,
        scopes,
        expires_in_days: expiresInDays ? Number(expiresInDays) : null,
      }),
    onSuccess: (res) => onCreated(res.token),
  });

  function toggleScope(scope: string) {
    setScopes((prev) => (prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]));
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <Field label="Name">
        <TextInput required value={name} onChange={(e) => setName(e.target.value)} placeholder="CI remediation runner" autoFocus />
      </Field>
      <Field label="Token Type">
        <Select
          value={tokenType}
          onChange={setTokenType}
          options={[
            { value: "personal", label: "Personal token" },
            { value: "service", label: "Service token" },
          ]}
          className="w-full"
        />
      </Field>
      <Field label="Scopes">
        <div className="max-h-56 space-y-3 overflow-y-auto rounded-lg border border-[#2a2a2a] p-3">
          {SCOPE_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-[#666]">{group.label}</div>
              <div className="space-y-1">
                {group.scopes.map((scope) => (
                  <label key={scope} className="flex items-center gap-2 text-sm text-[#ccc]">
                    <input type="checkbox" checked={scopes.includes(scope)} onChange={() => toggleScope(scope)} />
                    {scope}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Field>
      <Field label="Expiration">
        <Select value={expiresInDays} onChange={setExpiresInDays} options={EXPIRATION_OPTIONS} className="w-full" />
      </Field>
      <Button type="submit" className="w-full" disabled={create.isPending || scopes.length === 0}>
        {create.isPending ? "Creating…" : "Create Token"}
      </Button>
    </form>
  );
}

function WebhooksPanel() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  const { data: webhooks, isLoading } = useQuery({ queryKey: ["webhooks"], queryFn: () => api.get<Webhook[]>("/api/settings/webhooks") });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/api/settings/webhooks/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["webhooks"] });
      toast.success("Webhook deleted");
    },
  });

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button onClick={() => setCreateOpen(true)}>
          <Plus size={15} /> New Webhook
        </Button>
      </div>

      {!isLoading && webhooks?.length === 0 && <EmptyState icon={<WebhookIcon size={20} />} title="No webhooks configured" />}

      {webhooks?.map((w) => (
        <div key={w.id} className="mb-2 flex items-center justify-between rounded-xl border border-[#222] p-4">
          <div>
            <div className="font-mono text-sm text-white">{w.url}</div>
            <div className="mt-1 text-xs text-[#666]">{w.events.join(", ")}</div>
          </div>
          <Button variant="ghost" onClick={() => remove.mutate(w.id)}>
            Delete
          </Button>
        </div>
      ))}

      <NewWebhookModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(secret) => {
          queryClient.invalidateQueries({ queryKey: ["webhooks"] });
          setCreateOpen(false);
          setNewSecret(secret);
        }}
      />
      <Modal open={!!newSecret} onClose={() => setNewSecret(null)} title="Webhook created">
        <p className="mb-2 text-sm text-[#888]">Copy this signing secret now — you won't be able to see it again.</p>
        <div className="break-all rounded-lg border border-[#2a2a2a] bg-black p-3 font-mono text-xs text-emerald-400">{newSecret}</div>
      </Modal>
    </div>
  );
}

function NewWebhookModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (secret: string) => void }) {
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState<string[]>([]);

  const create = useMutation({
    mutationFn: () => api.post<Webhook>("/api/settings/webhooks", { url, events }),
    onSuccess: (res) => {
      setUrl("");
      setEvents([]);
      onClose();
      onCreated(res.secret);
    },
  });

  function toggleEvent(key: string) {
    if (key === "*") {
      setEvents((prev) => (prev.includes("*") ? [] : ["*"]));
      return;
    }
    setEvents((prev) => (prev.includes(key) ? prev.filter((e) => e !== key) : [...prev.filter((e) => e !== "*"), key]));
  }

  return (
    <Modal open={open} onClose={onClose} title="Create Webhook" description="Choose which events are delivered to your endpoint." width="max-w-xl">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Endpoint URL">
          <TextInput required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://automations.example.com/strix-webhook" autoFocus />
        </Field>
        <Field label="Events">
          <div className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-[#2a2a2a] p-2">
            {WEBHOOK_EVENTS.map((event) => (
              <label
                key={event.key}
                className={cn("flex items-start gap-2 rounded-lg p-2 text-sm", events.includes(event.key) && "bg-[rgba(255,255,255,0.05)]")}
              >
                <input type="checkbox" className="mt-1" checked={events.includes(event.key)} onChange={() => toggleEvent(event.key)} />
                <div>
                  <div className="text-white">{event.label}</div>
                  <div className="font-mono text-[10px] text-[#666]">{event.key}</div>
                  <div className="text-xs text-[#888]">{event.description}</div>
                </div>
              </label>
            ))}
          </div>
        </Field>
        <Button type="submit" className="w-full" disabled={create.isPending || !url.trim() || events.length === 0}>
          {create.isPending ? "Creating…" : "Create Webhook"}
        </Button>
      </form>
    </Modal>
  );
}
