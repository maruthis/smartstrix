import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "../../api/client";
import type { Issue, IssueDisposition, IssueStatus, Pentest } from "../../api/types";
import { QueryStatus } from "../../components/shared/EmptyState";
import { StatusPill } from "../../components/shared/StatusPill";
import { Button, Field, Select, TextArea } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";
import { formatDate } from "../../lib/format";

const STATUS_OPTIONS: { value: IssueStatus; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "in_progress", label: "In Progress" },
  { value: "snoozed", label: "Snoozed" },
  { value: "fixed", label: "Fixed" },
  { value: "ignored", label: "Ignored" },
];

const DISPOSITION_OPTIONS: { value: IssueDisposition; label: string }[] = [
  { value: "pending", label: "Pending review" },
  { value: "confirmed", label: "Confirmed" },
  { value: "rejected", label: "Rejected" },
  { value: "needs_repro", label: "Needs reproduction" },
  { value: "out_of_scope", label: "Out of scope" },
];

const SOURCE_LABELS: Record<string, string> = {
  baseline_scan: "Deterministic baseline",
  agent: "Agent analysis",
  mock: "Demo scanner",
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

  const [dispositionNote, setDispositionNote] = useState("");
  const [disposition, setDisposition] = useState<IssueDisposition>("pending");

  useEffect(() => {
    setDispositionNote(issue?.disposition_note ?? "");
    setDisposition(issue?.disposition ?? "pending");
  }, [issue?.id, issue?.disposition_note, issue?.disposition]);

  const updateStatus = useMutation({
    mutationFn: (status: IssueStatus) => api.patch<Issue>(`/api/issues/${id}/status`, { status }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["issue", id], updated);
      queryClient.invalidateQueries({ queryKey: ["issues"] });
      toast.success(`Marked as ${updated.status.replace(/_/g, " ")}`);
    },
  });

  const updateDisposition = useMutation({
    mutationFn: () =>
      api.patch<Issue>(`/api/issues/${id}/disposition`, {
        disposition,
        note: dispositionNote.trim(),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["issue", id], updated);
      queryClient.invalidateQueries({ queryKey: ["issues"] });
      queryClient.invalidateQueries({ queryKey: ["pentest-issues"] });
      toast.success(`Disposition: ${updated.disposition.replace(/_/g, " ")}`);
    },
    onError: () => {
      toast.error("A short note is required unless the finding stays pending.");
    },
  });

  const retest = useMutation({
    mutationFn: () => api.post<Pentest>(`/api/issues/${id}/retest`),
    onSuccess: (pentest) => {
      toast.success("Retest queued");
      navigate(`/pentests/${pentest.id}`);
    },
    onError: () => {
      toast.error("Could not queue a retest for this finding.");
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
            {issue.source === "agent" && <StatusPill value="agent" label="Agent analysis" />}
            {issue.source === "mock" && <StatusPill value="mock" label="Demo scanner" />}
            {issue.source === "mock_fallback" && <StatusPill value="mock_fallback" label="Mock fallback" />}
            <StatusPill value={issue.disposition ?? "pending"} />
            {issue.cvss !== null && <span className="text-xs text-[#666]">CVSS {issue.cvss.toFixed(1)}</span>}
          </div>
          <h1 className="text-lg font-semibold text-white">{issue.title}</h1>
          <div className="mt-1 text-xs text-[#666]">
            {issue.target} {issue.endpoint && `· ${issue.endpoint}`}
            {issue.file_path && ` · ${issue.file_path}${issue.line_number ? `:${issue.line_number}` : ""}`}
            {issue.specialist_name && ` · ${issue.specialist_name}`}
            · found {formatDate(issue.created_at)}
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
          {issue.source === "mock" || issue.source === "mock_fallback"
            ? "This is sample scanner content and must not be treated as evidence for this target."
            : issue.source === "baseline_scan"
              ? "This finding came from deterministic tooling. Validate exploitability and business impact before changing risk status."
              : "This finding was produced by agent analysis. Treat remediation guidance as a starting point and verify the evidence before closing."}
        </div>
        <div className="mb-5 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
          <div className="rounded-lg border border-[#222] bg-black/30 px-3 py-2">
            <div className="text-[#666]">Source</div>
            <div className="mt-0.5 text-[#ccc]">{SOURCE_LABELS[issue.source ?? "agent"] ?? issue.source ?? "Agent analysis"}</div>
          </div>
          <div className="rounded-lg border border-[#222] bg-black/30 px-3 py-2">
            <div className="text-[#666]">Location</div>
            <div className="mt-0.5 break-all text-[#ccc]">
              {issue.file_path
                ? `${issue.file_path}${issue.line_number ? `:${issue.line_number}` : ""}`
                : issue.endpoint || issue.target || "Not provided"}
            </div>
          </div>
          <div className="rounded-lg border border-[#222] bg-black/30 px-3 py-2">
            <div className="text-[#666]">Human disposition</div>
            <div className="mt-0.5 text-[#ccc]">{(issue.disposition ?? "pending").replace(/_/g, " ")}</div>
          </div>
        </div>
        <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Disposition">
            <Select
              value={disposition}
              onChange={(v) => setDisposition(v as IssueDisposition)}
              options={DISPOSITION_OPTIONS}
            />
          </Field>
          <Field label="Reviewer note" hint="Required to confirm, reject, or mark needs-repro / out-of-scope.">
            <TextArea value={dispositionNote} onChange={(e) => setDispositionNote(e.target.value)} rows={3} />
          </Field>
        </div>
        <div className="mb-5 flex flex-wrap gap-2">
          <Button
            type="button"
            onClick={() => updateDisposition.mutate()}
            disabled={updateDisposition.isPending}
          >
            {updateDisposition.isPending ? "Saving…" : "Save disposition"}
          </Button>
          <Button
            type="button"
            onClick={() => retest.mutate()}
            disabled={retest.isPending}
          >
            {retest.isPending ? "Queueing retest…" : "Retest this finding"}
          </Button>
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
