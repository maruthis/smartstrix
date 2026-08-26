import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ListChecks } from "lucide-react";
import { api } from "../../api/client";
import type { Issue, IssueStatus, IssuesResponse, Pentest, Repository } from "../../api/types";
import { EmptyState } from "../../components/shared/EmptyState";
import { StatusPill } from "../../components/shared/StatusPill";
import { FilterBar, Tabs } from "../../components/shared/FilterBar";
import { ListSelect } from "../../components/shared/ListSelect";
import { ViewToggle, type ViewMode } from "../../components/shared/ViewToggle";
import { Board } from "../../components/shared/Board";
import { timeAgo } from "../../lib/format";

const STATUS_TABS = [
  { key: "all", label: "All" },
  { key: "open", label: "Open" },
  { key: "in_progress", label: "In Progress" },
  { key: "snoozed", label: "Snoozed" },
  { key: "fixed", label: "Fixed" },
  { key: "ignored", label: "Ignored" },
];

const BOARD_COLUMNS: { key: IssueStatus; label: string }[] = [
  { key: "open", label: "Open" },
  { key: "in_progress", label: "In Progress" },
  { key: "snoozed", label: "Snoozed" },
  { key: "fixed", label: "Fixed" },
  { key: "ignored", label: "Ignored" },
];

export default function IssuesList() {
  const [status, setStatus] = useState("open");
  const [search, setSearch] = useState("");
  const [view, setView] = useState<ViewMode>("list");
  const [repositoryId, setRepositoryId] = useState("");
  const [pentestId, setPentestId] = useState("");

  const { data: repositories } = useQuery({
    queryKey: ["repositories"],
    queryFn: () => api.get<Repository[]>("/api/repositories"),
  });
  const { data: pentests } = useQuery({
    queryKey: ["pentests"],
    queryFn: () => api.get<Pentest[]>("/api/pentests"),
  });

  // Board mode always shows every status grouped into columns, so it fetches
  // unfiltered regardless of the status tab (which only applies to list mode).
  // Repository/pentest filters apply in both views — they narrow the actual
  // dataset, not just how the current status is displayed.
  const effectiveStatus = view === "board" ? "all" : status;
  const { data, isLoading } = useQuery({
    queryKey: ["issues", effectiveStatus, repositoryId, pentestId],
    queryFn: () => {
      const params = new URLSearchParams();
      if (effectiveStatus !== "all") params.set("status_filter", effectiveStatus);
      if (repositoryId) params.set("repository_id", repositoryId);
      if (pentestId) params.set("pentest_id", pentestId);
      const qs = params.toString();
      return api.get<IssuesResponse>(`/api/issues${qs ? `?${qs}` : ""}`);
    },
  });

  const items = (data?.items ?? []).filter((i) => i.title.toLowerCase().includes(search.toLowerCase()));

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-white">Issues</h1>

      <div className="mb-6 flex gap-8">
        {(["critical", "high", "medium", "low"] as const).map((s) => (
          <div key={s}>
            <div className="text-sm capitalize text-[#888]">{s}</div>
            <div className="text-2xl font-semibold text-white">{data?.severity_counts?.[s] ?? 0}</div>
          </div>
        ))}
      </div>

      {view === "list" && (
        <Tabs tabs={STATUS_TABS.map((t) => ({ ...t, count: data?.status_counts?.[t.key] ?? 0 }))} active={status} onChange={setStatus} />
      )}

      <FilterBar search={search} onSearch={setSearch} placeholder="Search issues...">
        <ListSelect
          value={repositoryId}
          onChange={setRepositoryId}
          ariaLabel="Filter by repository"
          options={[{ value: "", label: "All Repositories" }, ...(repositories ?? []).map((r) => ({ value: r.id, label: r.full_name }))]}
        />
        <ListSelect
          value={pentestId}
          onChange={setPentestId}
          ariaLabel="Filter by pentest"
          options={[
            { value: "", label: "All Pentests" },
            ...(pentests ?? []).map((p) => ({
              value: p.id,
              label: `${p.id.slice(0, 8)} · ${p.target_label} · ${timeAgo(p.created_at)}`,
            })),
          ]}
        />
        <ViewToggle view={view} onChange={setView} />
      </FilterBar>

      {!isLoading && items.length === 0 && <EmptyState icon={<ListChecks size={20} />} title="No issues" />}

      {items.length > 0 && view === "list" && (
        <div className="space-y-2">
          {items.map((issue) => (
            <IssueRow key={issue.id} issue={issue} />
          ))}
        </div>
      )}

      {items.length > 0 && view === "board" && (
        <Board
          columns={BOARD_COLUMNS.map((col) => ({ ...col, items: items.filter((i) => i.status === col.key) }))}
          renderCard={(issue) => <IssueCard issue={issue} />}
        />
      )}
    </div>
  );
}

function IssueRow({ issue }: { issue: Issue }) {
  return (
    <Link
      to={`/issues/${issue.id}`}
      className="flex items-center justify-between rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-4 hover:border-[#333]"
    >
      <div>
        <div className="text-sm text-white">{issue.title}</div>
        <div className="mt-1 text-xs text-[#666]">
          {issue.target} · {timeAgo(issue.created_at)}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <StatusPill value={issue.status} />
        <StatusPill value={issue.severity} />
        {issue.source === "baseline_scan" && (
          <StatusPill value="baseline_scan" label="Automatically detected" />
        )}
        {issue.source === "mock_fallback" && <StatusPill value="mock_fallback" label="Mock fallback" />}
      </div>
    </Link>
  );
}

function IssueCard({ issue }: { issue: Issue }) {
  return (
    <Link to={`/issues/${issue.id}`} className="block rounded-lg border border-[#222] bg-[rgba(255,255,255,0.02)] p-3 hover:border-[#333]">
      <div className="mb-2 text-sm text-white">{issue.title}</div>
      <div className="flex items-center justify-between">
        <StatusPill value={issue.severity} />
        <span className="text-[10px] text-[#666]">{timeAgo(issue.created_at)}</span>
      </div>
    </Link>
  );
}
