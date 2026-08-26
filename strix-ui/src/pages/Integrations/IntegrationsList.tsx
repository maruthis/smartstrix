import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Github, Gitlab, GitFork, Slack, MessagesSquare, KanbanSquare, Ticket, ExternalLink, type LucideIcon } from "lucide-react";
import { api } from "../../api/client";
import type { Integration } from "../../api/types";
import { Button } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";
import { ConnectProviderModal } from "./ConnectProviderModal";

const PROVIDER_ICONS: Record<string, LucideIcon> = {
  github: Github,
  gitlab: Gitlab,
  bitbucket: GitFork,
  slack: Slack,
  msteams: MessagesSquare,
  jira: KanbanSquare,
  linear: Ticket,
};

const SECTIONS: { category: Integration["category"]; title: string; description: string }[] = [
  { category: "code", title: "Code Providers", description: "Connect your repositories for source-aware pentesting." },
  { category: "communication", title: "Communication", description: "Get notified about test results and findings in your team channels." },
  { category: "issue_tracking", title: "Issue Tracking", description: "Two-way sync vulnerabilities and their status with your ticketing tools." },
];

export default function IntegrationsList() {
  const queryClient = useQueryClient();
  const [connectTarget, setConnectTarget] = useState<Integration | null>(null);
  const { data: integrations } = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.get<Integration[]>("/api/integrations"),
  });

  const disconnect = useMutation({
    mutationFn: (provider: string) => api.delete<Integration>(`/api/integrations/${provider}`),
    onSuccess: (updated) => {
      queryClient.setQueryData<Integration[]>(["integrations"], (prev) =>
        prev?.map((i) => (i.provider === updated.provider ? updated : i))
      );
      toast.success(`${updated.label} disconnected`);
    },
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">Integrations</h1>

      {SECTIONS.map((section) => {
        const items = integrations?.filter((i) => i.category === section.category) ?? [];
        if (integrations && items.length === 0) return null;
        return (
          <div key={section.category} className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)]">
            <div className="border-b border-[#1a1a1a] p-5 pb-4">
              <h2 className="text-sm font-medium text-white">{section.title}</h2>
              <p className="mt-1 text-xs text-[#666]">{section.description}</p>
            </div>
            <div>
              {items.map((integration) => (
                <IntegrationRow
                  key={integration.provider}
                  integration={integration}
                  onConnect={() => setConnectTarget(integration)}
                  onDisconnect={() => disconnect.mutate(integration.provider)}
                  pending={disconnect.isPending}
                />
              ))}
            </div>
          </div>
        );
      })}

      <ConnectProviderModal integration={connectTarget} onClose={() => setConnectTarget(null)} />
    </div>
  );
}

function IntegrationRow({
  integration,
  onConnect,
  onDisconnect,
  pending,
}: {
  integration: Integration;
  onConnect: () => void;
  onDisconnect: () => void;
  pending: boolean;
}) {
  const navigate = useNavigate();
  const Icon = PROVIDER_ICONS[integration.provider] ?? Github;
  return (
    <div className="flex items-center justify-between border-b border-[#1a1a1a] px-5 py-4 last:border-0">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-[#2a2a2a] bg-black text-white">
          <Icon size={17} />
        </div>
        <div>
          <div className="flex items-center gap-2 text-sm text-white">
            {integration.label}
            {integration.status === "connected" && (
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                Connected
              </span>
            )}
          </div>
          {integration.status === "connected" && integration.account_label && (
            <div className="text-xs text-[#666]">
              {integration.account_label}
              {integration.base_url && <span className="text-[#555]"> · {integration.base_url}</span>}
              {integration.credential_last4 && <span className="text-[#555]"> · token ending in {integration.credential_last4}</span>}
            </div>
          )}
        </div>
      </div>

      {integration.coming_soon ? (
        <span className="text-xs text-[#555]">Coming soon</span>
      ) : integration.status === "connected" ? (
        <div className="flex items-center gap-4 text-xs">
          {integration.provider === "github" && (
            <button className="text-[#aaa] hover:text-white" onClick={() => navigate("/repositories")}>
              Connect more
            </button>
          )}
          {integration.configure_url && (
            <a
              href={integration.configure_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-[#aaa] hover:text-white"
            >
              Configure <ExternalLink size={11} />
            </a>
          )}
          <button className="text-red-400 hover:text-red-300" onClick={onDisconnect} disabled={pending}>
            Disconnect
          </button>
        </div>
      ) : (
        <Button variant="secondary" onClick={onConnect}>
          Connect
        </Button>
      )}
    </div>
  );
}
