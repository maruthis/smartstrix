import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clock, Download, Eye, Loader2 } from "lucide-react";
import { api } from "../../api/client";
import type { Issue, PentestLogsResponse, PRReview } from "../../api/types";
import { StatusPill } from "../../components/shared/StatusPill";
import { QueryStatus } from "../../components/shared/EmptyState";
import { formatDate } from "../../lib/format";
import { PentestLogViewer } from "../Pentests/PentestLogViewer";

// Statuses that mean the scan has actually finished — a report only exists
// once one of these is reached (mirrors app/routers/pr_reviews.py's
// _DONE_STATUSES; "running" has nothing yet and "failed" has no findings
// and no report worth generating).
const DONE_STATUSES = new Set(["awaiting_merge", "needs_attention", "merged_with_open_findings", "passed"]);

function useElapsedLabel(startedAt: string | null): string | null {
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!startedAt) return;
    const interval = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(interval);
  }, [startedAt]);

  if (!startedAt) return null;
  const started = new Date(startedAt.endsWith("Z") ? startedAt : startedAt + "Z").getTime();
  const elapsedSec = Math.max(0, Math.floor((Date.now() - started) / 1000));
  const mins = Math.floor(elapsedSec / 60);
  const secs = elapsedSec % 60;
  return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
}

export default function PRReviewDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: review, isLoading, isError } = useQuery({
    queryKey: ["pr-review", id],
    queryFn: () => api.get<PRReview>(`/api/pr-reviews/${id}`),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
  });

  const { data: issues } = useQuery({
    queryKey: ["pr-review-issues", id],
    queryFn: () => api.get<Issue[]>(`/api/pr-reviews/${id}/issues`),
    enabled: !!review && review.status !== "running",
  });

  // PRReview has no distinct started_at — the row is created right when
  // the scan is enqueued, so created_at is effectively the start time.
  const elapsed = useElapsedLabel(review?.status === "running" ? (review?.created_at ?? null) : null);

  if (isLoading || isError || !review) return <QueryStatus isLoading={isLoading} />;

  const running = review.status === "running";
  const failed = review.status === "failed";
  const done = DONE_STATUSES.has(review.status);

  return (
    <div className="mx-auto max-w-3xl">
      <button onClick={() => navigate("/pr-reviews")} className="mb-4 flex items-center gap-1.5 text-sm text-[#888] hover:text-white">
        <ArrowLeft size={14} /> PR Reviews
      </button>

      <div className="mb-6 rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-6">
        <div className="mb-1 flex items-center gap-2">
          <h1 className="text-lg font-semibold text-white">
            {review.repository_full_name} <span className="text-[#666]">#{review.pr_number}</span>
          </h1>
          <StatusPill value={review.status} />
        </div>
        <div className="text-sm text-[#888]">{review.title}</div>
        <div className="mt-1 text-xs text-[#666]">
          by {review.author} · created {formatDate(review.created_at)}
        </div>
        <div className="mt-1 font-mono text-xs text-[#555]" title={review.id}>
          {review.id}
        </div>
        {(review.target_branch || review.resolved_head_sha) && (
          <div className="mt-1 text-xs text-[#666]">
            {review.target_branch && <>base: <span className="font-mono">{review.target_branch}</span></>}
            {review.resolved_head_sha && (
              <>
                {review.target_branch && " · "}
                commit{" "}
                <span className="font-mono" title={review.resolved_head_sha}>
                  {review.resolved_head_sha.slice(0, 12)}
                </span>
              </>
            )}
          </div>
        )}

        {running && (
          <div className="mt-6">
            <div className="flex items-center gap-2 text-sm text-[#ccc]">
              <Loader2 size={16} className="animate-spin text-white" />
              <span>Scanning this pull request's changes… findings will appear below once the scan finishes.</span>
              {elapsed && (
                <span className="ml-auto flex items-center gap-1 text-xs text-[#666]">
                  <Clock size={12} />
                  {elapsed} elapsed
                </span>
              )}
            </div>

            <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-[#1a1a1a]">
              <div className="h-full w-1/3 rounded-full bg-white animate-indeterminate-bar" />
            </div>

            <p className="mt-3 rounded-lg border border-[#222] bg-[rgba(255,255,255,0.02)] px-3 py-2 text-xs text-[#888]">
              This review is running in the background. Feel free to navigate away or close this tab — the scan will
              keep going, and you can come back to this page anytime to check progress or view the Run Log below.
            </p>
          </div>
        )}

        {failed && (
          <p className="mt-6 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2 text-sm text-red-300">
            This review failed{review.error ? `: ${review.error}` : "."} No report is available for a failed run.
          </p>
        )}

        {done && (
          <div className="mt-6 flex items-center gap-6">
            <div className="flex gap-4">
              {(["critical", "high", "medium", "low"] as const).map((s) => (
                <div key={s}>
                  <div className="text-2xl font-semibold text-white">
                    {issues?.filter((i) => i.severity === s).length ?? 0}
                  </div>
                  <div className="text-xs capitalize text-[#888]">{s}</div>
                </div>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-3">
              <a
                href={`/api/pr-reviews/${review.id}/report`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 rounded-lg border border-[#2a2a2a] px-3 py-1.5 text-sm text-white hover:bg-[rgba(255,255,255,0.06)]"
              >
                <Eye size={14} /> View report
              </a>
              <a
                href={`/api/pr-reviews/${review.id}/report/download`}
                className="flex items-center gap-1.5 rounded-lg border border-[#2a2a2a] px-3 py-1.5 text-sm text-white hover:bg-[rgba(255,255,255,0.06)]"
              >
                <Download size={14} /> Download PDF
              </a>
            </div>
          </div>
        )}
      </div>

      {issues && issues.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-3 text-sm font-medium text-white">Findings</h2>
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

      {done && issues?.length === 0 && <p className="mb-6 text-sm text-[#666]">No findings from this review.</p>}

      <PRReviewLogsSection reviewId={review.id} running={running} />
    </div>
  );
}

function PRReviewLogsSection({ reviewId, running }: { reviewId: string; running: boolean }) {
  const [level, setLevel] = useState("");
  const [agentId, setAgentId] = useState("");
  const [query, setQuery] = useState("");

  const { data } = useQuery({
    queryKey: ["pr-review-logs", reviewId, level, agentId, query],
    queryFn: () =>
      api.get<PentestLogsResponse>(
        `/api/pr-reviews/${reviewId}/logs?` +
          new URLSearchParams({
            ...(level ? { level } : {}),
            ...(agentId ? { agent_id: agentId } : {}),
            ...(query ? { q: query } : {}),
          }).toString()
      ),
    refetchInterval: running ? 3000 : false,
  });

  return (
    <div>
      <h2 className="mb-3 text-sm font-medium text-white">Run Log</h2>
      <PentestLogViewer
        data={data}
        level={level}
        onLevel={setLevel}
        agentId={agentId}
        onAgentId={setAgentId}
        query={query}
        onQuery={setQuery}
        emptyDescription="This PR review predates run-log capture, or hasn't started yet."
      />
    </div>
  );
}
