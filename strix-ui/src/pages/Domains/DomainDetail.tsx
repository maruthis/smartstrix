import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ShieldCheck, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import type { DomainOut, Issue, Pentest } from "../../api/types";
import { StatusPill } from "../../components/shared/StatusPill";
import { QueryStatus } from "../../components/shared/EmptyState";
import { Button } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";
import { timeAgo } from "../../lib/format";

export default function DomainDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: domain, isLoading, isError } = useQuery({
    queryKey: ["domain", id],
    queryFn: () => api.get<DomainOut>(`/api/domains/${id}`),
  });

  const { data: pentests } = useQuery({
    queryKey: ["pentests", { target_id: id }],
    queryFn: () => api.get<Pentest[]>(`/api/pentests?target_type=domain&target_id=${id}`),
    enabled: !!domain,
  });

  const { data: issues } = useQuery({
    queryKey: ["issues", { domain_id: id }],
    queryFn: () => api.get<{ items: Issue[] }>(`/api/issues?domain_id=${id}`).then((r) => r.items),
    enabled: !!domain,
  });

  const verify = useMutation({
    mutationFn: () => api.post<DomainOut>(`/api/domains/${id}/verify`),
    onSuccess: (updated) => {
      queryClient.setQueryData(["domain", id], updated);
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      toast.success("Domain verified");
    },
  });

  const scan = useMutation({
    mutationFn: () => api.post<{ pentest_id: string }>(`/api/domains/${id}/scan`),
    onSuccess: (res) => navigate(`/pentests/${res.pentest_id}`),
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/api/domains/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      toast.success("Domain removed");
      navigate("/domains");
    },
  });

  if (isLoading || isError || !domain) return <QueryStatus isLoading={isLoading} />;

  return (
    <div className="mx-auto max-w-3xl">
      <button onClick={() => navigate("/domains")} className="mb-4 flex items-center gap-1.5 text-sm text-[#888] hover:text-white">
        <ArrowLeft size={14} /> Domains
      </button>

      <div className="mb-6 rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-6">
        <div className="mb-1 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-white">{domain.hostname}</h1>
            <StatusPill value={domain.verified ? "verified" : "queued"} label={domain.verified ? "Verified" : "Unverified"} />
          </div>
          <button
            onClick={() => {
              if (window.confirm(`Remove ${domain.hostname}? This cannot be undone.`)) remove.mutate();
            }}
            className="text-[#666] hover:text-red-400"
          >
            <Trash2 size={15} />
          </button>
        </div>
        <div className="text-sm text-[#888]">{domain.last_tested_at ? `Last tested ${timeAgo(domain.last_tested_at)}` : "Never tested"}</div>

        {!domain.verified && (
          <div className="mt-4 rounded-lg border border-[#2a2a2a] bg-black p-4">
            <div className="mb-1 text-sm font-medium text-white">Verify ownership</div>
            <p className="mb-3 text-xs text-[#888]">
              Add the following as a {domain.verification_method === "dns_txt" ? "DNS TXT record" : "file"} for {domain.hostname}, then
              verify:
            </p>
            <div className="mb-3 break-all rounded-lg border border-[#2a2a2a] bg-[rgba(255,255,255,0.03)] p-3 font-mono text-xs text-emerald-400">
              {domain.verification_token}
            </div>
            <Button variant="secondary" onClick={() => verify.mutate()} disabled={verify.isPending}>
              <ShieldCheck size={14} /> I've added it — verify now
            </Button>
          </div>
        )}

        {domain.verified && (
          <div className="mt-4">
            <Button onClick={() => scan.mutate()} disabled={scan.isPending}>
              {scan.isPending ? "Starting…" : "Run scan"}
            </Button>
          </div>
        )}
      </div>

      <div className="mb-6">
        <h2 className="mb-3 text-sm font-medium text-white">Scan history</h2>
        {pentests?.length === 0 && <p className="text-sm text-[#666]">No scans yet.</p>}
        <div className="space-y-2">
          {pentests?.map((p) => (
            <Link
              key={p.id}
              to={`/pentests/${p.id}`}
              className="flex items-center justify-between rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-4 hover:border-[#333]"
            >
              <span className="text-sm text-white">{p.scan_mode} scan</span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-[#666]">{timeAgo(p.created_at)}</span>
                <StatusPill value={p.status} />
              </div>
            </Link>
          ))}
        </div>
      </div>

      {issues && issues.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-medium text-white">Open findings</h2>
          <div className="space-y-2">
            {issues.map((issue) => (
              <Link
                key={issue.id}
                to={`/issues/${issue.id}`}
                className="flex items-center justify-between rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-4 hover:border-[#333]"
              >
                <span className="text-sm text-white">{issue.title}</span>
                <StatusPill value={issue.severity} />
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
