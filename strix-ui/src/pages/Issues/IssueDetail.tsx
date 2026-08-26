import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "../../api/client";
import type { Issue, IssueStatus } from "../../api/types";
import { QueryStatus } from "../../components/shared/EmptyState";
import { StatusPill } from "../../components/shared/StatusPill";
import { Select } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";
import { formatDate } from "../../lib/format";

const STATUS_OPTIONS: { value: IssueStatus; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "snoozed", label: "Snoozed" },
  { value: "fixed", label: "Fixed" },
  { value: "ignored", label: "Ignored" },
];

const SOURCE_LABELS: Record<string, string> = {
  baseline_scan: "Deterministic scanner",
  mock_fallback: "Sample fallback",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  if (!children) return null;
  return (
    <div className="mb-5">
      <h3 className="mb-1.5 text-sm font-medium text-white">{title}</h3>
      <div className="whitespace-pre-wrap text-sm leading-relaxed text-[#aaa]">{children}</div>
    </div>
  );
}

export default function IssueDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: issue, isLoading, isError } = useQuery({
    queryKey: ["issue", id],
    queryFn: () => api.get<Issue>(`/api/issues/${id}`),
  });

  const updateStatus = useMutation({
    mutationFn: (status: IssueStatus) => api.patch<Issue>(`/api/issues/${id}/status`, { status }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["issue", id], updated);
      queryClient.invalidateQueries({ queryKey: ["issues"] });
      toast.success(`Marked as ${updated.status.replace(/_/g, " ")}`);
    },
  });

  if (isLoading || isError || !issue) return <QueryStatus isLoading={isLoading} />;

  return (
    <div className="mx-auto max-w-3xl">
      <button onClick={() => navigate(-1)} className="mb-4 flex items-center gap-1.5 text-sm text-[#888] hover:text-white">
        <ArrowLeft size={14} /> Back
      </button>

      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <StatusPill value={issue.severity} />
            {issue.source === "baseline_scan" && (
              <StatusPill value="baseline_scan" label="Automatically detected" />
            )}
            {issue.source === "mock_fallback" && <StatusPill value="mock_fallback" label="Mock fallback" />}
            {issue.cvss !== null && <span className="text-xs text-[#666]">CVSS {issue.cvss.toFixed(1)}</span>}
          </div>
          <h1 className="text-lg font-semibold text-white">{issue.title}</h1>
          <div className="mt-1 text-xs text-[#666]">
            {issue.target} {issue.endpoint && `· ${issue.endpoint}`} · found {formatDate(issue.created_at)}
          </div>
        </div>
        <Select
          value={issue.status}
          onChange={(v) => updateStatus.mutate(v as IssueStatus)}
          options={STATUS_OPTIONS}
        />
      </div>

      <div className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-6">
        <div className="mb-5 rounded-lg border border-[#2a2a2a] bg-black/40 px-3 py-2 text-xs leading-relaxed text-[#888]">
          <span className="font-medium text-[#ccc]">Review posture:</span>{" "}
          {issue.source === "mock_fallback"
            ? "This is sample fallback content and must not be treated as evidence for this target."
            : issue.source === "baseline_scan"
              ? "This finding came from deterministic tooling. Validate exploitability and business impact before changing risk status."
              : "This finding was produced by agent analysis. Treat remediation guidance as a starting point and verify the evidence before closing."}
        </div>
        <div className="mb-5 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
          <div className="rounded-lg border border-[#222] bg-black/30 px-3 py-2">
            <div className="text-[#666]">Source</div>
            <div className="mt-0.5 text-[#ccc]">{issue.source ? SOURCE_LABELS[issue.source] ?? issue.source : "Agent validated"}</div>
          </div>
          <div className="rounded-lg border border-[#222] bg-black/30 px-3 py-2">
            <div className="text-[#666]">Evidence target</div>
            <div className="mt-0.5 break-all text-[#ccc]">{issue.endpoint || issue.target || "Not provided"}</div>
          </div>
          <div className="rounded-lg border border-[#222] bg-black/30 px-3 py-2">
            <div className="text-[#666]">Human review</div>
            <div className="mt-0.5 text-[#ccc]">{issue.status === "fixed" || issue.status === "ignored" ? "Decision recorded" : "Pending decision"}</div>
          </div>
        </div>
        <Section title="Description">{issue.description}</Section>
        <Section title="Technical analysis">{issue.technical_analysis}</Section>
        <Section title="Proof of concept">{issue.poc_description}</Section>
        <Section title="Remediation">{issue.remediation_steps}</Section>
        <div className="text-xs text-[#555]">Fix effort: {issue.fix_effort}</div>
      </div>
    </div>
  );
}
