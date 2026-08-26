import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, GitPullRequest, Github, Gitlab, Plus, Settings as SettingsIcon, X } from "lucide-react";
import { api, ApiError } from "../../api/client";
import type { PRReview, PRReviewsResponse, PRReviewSettings, PRReviewStatus, Repository, RepoPullRequest, Severity } from "../../api/types";
import { EmptyState } from "../../components/shared/EmptyState";
import { Modal } from "../../components/shared/Modal";
import { AddRepositoryModal } from "../../components/shared/AddRepositoryModal";
import { StatusPill } from "../../components/shared/StatusPill";
import { Tabs, FilterBar } from "../../components/shared/FilterBar";
import { Button, Field, Select, TextInput, Toggle } from "../../components/shared/Form";
import { ViewToggle, type ViewMode } from "../../components/shared/ViewToggle";
import { Board } from "../../components/shared/Board";
import { toast } from "../../components/shared/Toast";
import { timeAgo } from "../../lib/format";
import { useDebouncedValue } from "../../lib/useDebouncedValue";

const TABS = [
  { key: "all", label: "All" },
  { key: "awaiting_merge", label: "Awaiting Merge" },
  { key: "needs_attention", label: "Needs Attention" },
  { key: "merged_with_open_findings", label: "Merged with Open Findings" },
  { key: "passed", label: "Passed" },
];

const BOARD_COLUMNS: { key: PRReviewStatus; label: string }[] = [
  { key: "running", label: "Running" },
  { key: "awaiting_merge", label: "Awaiting Merge" },
  { key: "needs_attention", label: "Needs Attention" },
  { key: "merged_with_open_findings", label: "Merged with Open Findings" },
  { key: "passed", label: "Passed" },
  { key: "failed", label: "Failed" },
];

function repositoryProviderLabel(provider: string) {
  return provider === "gitlab" ? "GitLab" : "GitHub";
}

function RepositoryProviderIcon({ provider, className }: { provider: string; className?: string }) {
  const Icon = provider === "gitlab" ? Gitlab : Github;
  return <Icon size={15} className={className} />;
}

function pullRequestFetchErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 401) return "The connected provider credential was rejected. Reconnect the integration, then retry.";
    if (error.status === 502) return "The provider API could not be reached. Check the integration URL/token and retry.";
    if (error.detail) return `Could not load open pull requests: ${error.detail}`;
  }
  return "Could not load open pull requests. You can retry or enter the PR number manually.";
}

export default function PRReviewsList() {
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");
  const [view, setView] = useState<ViewMode>("list");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [connectOpen, setConnectOpen] = useState(false);

  // Board mode always shows every status grouped into columns, so it ignores
  // the status tab (which only applies to list mode).
  const effectiveStatus = view === "board" ? "all" : status;
  const debouncedSearch = useDebouncedValue(search, 300);
  const { data, isLoading } = useQuery({
    queryKey: ["pr-reviews", effectiveStatus, debouncedSearch],
    queryFn: () =>
      api.get<PRReviewsResponse>(
        `/api/pr-reviews?${effectiveStatus !== "all" ? `status_filter=${effectiveStatus}&` : ""}${debouncedSearch ? `search=${encodeURIComponent(debouncedSearch)}` : ""}`
      ),
    // A triggered review runs a real scan and starts out "running" — poll
    // so its row updates to a final status without a manual refresh.
    refetchInterval: 4000,
  });

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">PR Reviews</h1>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => setSettingsOpen(true)}>
            <SettingsIcon size={15} /> Settings
          </Button>
          <Button variant="secondary" onClick={() => setConnectOpen(true)}>
            <Plus size={15} /> Connect Repository
          </Button>
          <Button onClick={() => setReviewOpen(true)}>Review a Pull Request</Button>
        </div>
      </div>

      <div className="mb-4 flex items-center gap-2 rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2 text-sm text-blue-300">
        Tip — Tag <code className="rounded bg-blue-500/10 px-1">@strix</code> on any pull request to run a security review.
      </div>

      {view === "list" && <Tabs tabs={TABS.map((t) => ({ ...t, count: data?.counts?.[t.key] ?? 0 }))} active={status} onChange={setStatus} />}

      <FilterBar search={search} onSearch={setSearch} placeholder="Search repository, title, or PR number">
        <ViewToggle view={view} onChange={setView} />
      </FilterBar>

      {!isLoading && data?.items.length === 0 && (
        <EmptyState icon={<GitPullRequest size={20} />} title="No PR reviews" description="Tag @strix on any pull request to run a security review." />
      )}

      {data && data.items.length > 0 && view === "list" && (
        <div className="space-y-2">
          {data.items.map((r) => (
            <PRReviewRow key={r.id} review={r} />
          ))}
        </div>
      )}

      {data && data.items.length > 0 && view === "board" && (
        <Board
          columns={BOARD_COLUMNS.map((col) => ({ ...col, items: data.items.filter((r) => r.status === col.key) }))}
          renderCard={(r) => <PRReviewCard review={r} />}
        />
      )}

      <PRReviewSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <TriggerReviewModal open={reviewOpen} onClose={() => setReviewOpen(false)} />
      <AddRepositoryModal open={connectOpen} onClose={() => setConnectOpen(false)} />
    </div>
  );
}

// Statuses that mean the scan has actually finished — a report only exists
// once one of these is reached (mirrors app/routers/pr_reviews.py's
// _DONE_STATUSES).
const DONE_STATUSES = new Set(["awaiting_merge", "needs_attention", "merged_with_open_findings", "passed"]);

function ReportLinks({ reviewId }: { reviewId: string }) {
  return (
    <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
      <a href={`/api/pr-reviews/${reviewId}/report`} target="_blank" rel="noreferrer" title="View report" className="text-[#888] hover:text-white">
        <Eye size={16} />
      </a>
      <a href={`/api/pr-reviews/${reviewId}/report/download`} title="Download report (PDF)" className="text-[#888] hover:text-white">
        <Download size={16} />
      </a>
    </div>
  );
}

function PRReviewRow({ review: r }: { review: PRReview }) {
  const navigate = useNavigate();
  return (
    <div
      onClick={() => navigate(`/pr-reviews/${r.id}`)}
      className="flex cursor-pointer items-center justify-between rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-4 hover:border-[#333]"
    >
      <div>
        <div className="text-sm text-white">
          {r.repository_full_name} <span className="text-[#666]">#{r.pr_number}</span> — {r.title}
        </div>
        <div className="mt-1 text-xs text-[#666]">
          by {r.author} · {timeAgo(r.updated_at)} · {r.status === "running" ? "scanning…" : `${r.findings_count} finding(s)`}
        </div>
        {r.status === "failed" && r.error && <div className="mt-1 text-xs text-red-400">{r.error}</div>}
      </div>
      <div className="flex items-center gap-3">
        {DONE_STATUSES.has(r.status) && <ReportLinks reviewId={r.id} />}
        <StatusPill value={r.status} />
      </div>
    </div>
  );
}

function PRReviewCard({ review: r }: { review: PRReview }) {
  const navigate = useNavigate();
  return (
    <div
      onClick={() => navigate(`/pr-reviews/${r.id}`)}
      className="cursor-pointer rounded-lg border border-[#222] bg-[rgba(255,255,255,0.02)] p-3 hover:border-[#333]"
    >
      <div className="mb-1 text-sm text-white">
        {r.repository_full_name} <span className="text-[#666]">#{r.pr_number}</span>
      </div>
      <div className="mb-2 text-xs text-[#888]">{r.title}</div>
      <div className="flex items-center justify-between text-[10px] text-[#666]">
        <span>{r.author}</span>
        <div className="flex items-center gap-2">
          {DONE_STATUSES.has(r.status) && <ReportLinks reviewId={r.id} />}
          <span>{r.status === "running" ? "scanning…" : `${r.findings_count} finding(s)`}</span>
        </div>
      </div>
    </div>
  );
}

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];

function PRReviewSettingsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: settings } = useQuery({
    queryKey: ["pr-review-settings"],
    queryFn: () => api.get<PRReviewSettings>("/api/pr-reviews/settings"),
    enabled: open,
  });

  const update = useMutation({
    mutationFn: (patch: Partial<PRReviewSettings>) => api.patch<PRReviewSettings>("/api/pr-reviews/settings", patch),
    onSuccess: (updated) => queryClient.setQueryData(["pr-review-settings"], updated),
  });

  if (!settings) return <Modal open={open} onClose={onClose} title="PR Review Settings" children={null} />;

  return (
    <Modal open={open} onClose={onClose} title="PR Review Settings" description="Configure how reviews are triggered and billed." width="max-w-xl">
      <div className="max-h-[70vh] space-y-5 overflow-y-auto pr-1">
        <ToggleRow label="Re-review on push" checked={settings.rereview_on_push} onChange={(v) => update.mutate({ rereview_on_push: v })} />

        <TagListField
          label="Target branches"
          placeholder="branch or pattern…"
          values={settings.target_branches}
          onChange={(target_branches) => update.mutate({ target_branches })}
        />

        <ToggleRow label="Approve clean PRs" checked={settings.approve_clean_prs} onChange={(v) => update.mutate({ approve_clean_prs: v })} />

        <ToggleRow
          label="Block PRs on findings"
          checked={settings.block_prs_on_findings}
          onChange={(v) => update.mutate({ block_prs_on_findings: v })}
        />
        {settings.block_prs_on_findings && (
          <div className="-mt-3 flex gap-2 pl-1">
            {SEVERITIES.map((s) => {
              const active = settings.blocking_severities.includes(s);
              return (
                <button
                  key={s}
                  onClick={() =>
                    update.mutate({
                      blocking_severities: active
                        ? settings.blocking_severities.filter((x) => x !== s)
                        : [...settings.blocking_severities, s],
                    })
                  }
                  className={`rounded-full border px-3 py-1 text-xs capitalize transition-colors ${
                    active ? "border-white/40 bg-white/10 text-white" : "border-[#2a2a2a] text-[#666]"
                  }`}
                >
                  {s}
                </button>
              );
            })}
          </div>
        )}

        <ToggleRow
          label="Exclude bot accounts"
          checked={settings.exclude_bot_accounts}
          onChange={(v) => update.mutate({ exclude_bot_accounts: v })}
        />
        <TagListField
          label="Excluded usernames"
          placeholder="username…"
          values={settings.excluded_usernames}
          onChange={(excluded_usernames) => update.mutate({ excluded_usernames })}
        />

        <ToggleRow
          label="Allow overage reviews"
          checked={settings.allow_overage_reviews}
          onChange={(v) => update.mutate({ allow_overage_reviews: v })}
        />

        <Field label="Review cap per developer">
          <div className="flex items-center gap-2">
            <TextInput
              type="number"
              placeholder="No cap"
              defaultValue={settings.review_cap_per_dev ?? ""}
              onBlur={(e) => update.mutate({ review_cap_per_dev: e.target.value ? Number(e.target.value) : null })}
              className="w-28"
            />
            <span className="text-xs text-[#666]">reviews / dev / {settings.review_cap_period}</span>
          </div>
        </Field>
      </div>
    </Modal>
  );
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-white">{label}</span>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}

function TagListField({
  label,
  placeholder,
  values,
  onChange,
}: {
  label: string;
  placeholder: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const value = draft.trim();
    if (value && !values.includes(value)) onChange([...values, value]);
    setDraft("");
  }

  return (
    <Field label={label}>
      <div className="flex gap-2">
        <TextInput
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
        />
        <Button type="button" variant="secondary" onClick={add}>
          + Add
        </Button>
      </div>
      {values.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {values.map((v) => (
            <span key={v} className="flex items-center gap-1 rounded-full border border-[#2a2a2a] px-2.5 py-1 text-xs text-[#ccc]">
              {v}
              <button type="button" onClick={() => onChange(values.filter((x) => x !== v))} className="text-[#666] hover:text-white">
                <X size={11} />
              </button>
            </span>
          ))}
        </div>
      )}
    </Field>
  );
}

function TriggerReviewModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: repos } = useQuery({ queryKey: ["repositories"], queryFn: () => api.get<Repository[]>("/api/repositories"), enabled: open });
  const [selectedRepo, setSelectedRepo] = useState<Repository | null>(null);
  const [manualEntry, setManualEntry] = useState(false);
  const [prNumber, setPrNumber] = useState("");
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [targetBranch, setTargetBranch] = useState("");

  const { data: pullRequests, error: pullRequestsError, isError: prsError, isFetching: prsLoading, refetch: refetchPullRequests } = useQuery({
    queryKey: ["repository-pull-requests", selectedRepo?.id, selectedRepo?.provider, selectedRepo?.full_name],
    queryFn: () => api.get<RepoPullRequest[]>(`/api/repositories/${selectedRepo!.id}/pull-requests`),
    enabled: !!selectedRepo,
    retry: false,
  });
  const openPullRequests = pullRequests ?? [];
  const selectedOpenPullRequest = openPullRequests.find((pr) => String(pr.number) === prNumber) ?? openPullRequests[0] ?? null;
  const reposLoaded = !!repos;
  const selectedRepoId = selectedRepo?.id ?? "";
  const requestLabel = selectedRepo?.provider === "gitlab" ? "merge request" : "pull request";
  const requestLabelPlural = selectedRepo?.provider === "gitlab" ? "merge requests" : "pull requests";
  const providerOptions = [
    {
      value: "",
      label: !reposLoaded ? "Loading repositories..." : repos.length === 0 ? "No connected repositories found" : "Select repository",
      disabled: true,
    },
    ...(repos ?? []).map((repo) => ({
      value: repo.id,
      label: `${repo.full_name} (${repositoryProviderLabel(repo.provider)})`,
    })),
  ];
  const pullRequestOptions = [
    {
      value: "",
      label: !selectedRepo
        ? "Select a repository first"
        : prsLoading
          ? `Loading open ${requestLabelPlural}...`
          : openPullRequests.length === 0
            ? `No open ${requestLabelPlural} found`
            : `Select ${requestLabel}`,
      disabled: true,
    },
    ...openPullRequests.map((pr) => ({ value: String(pr.number), label: `#${pr.number}` })),
  ];
  const pullRequestTitleOptions = [
    {
      value: "",
      label: !selectedRepo
        ? "Select a repository first"
        : prsLoading
          ? `Loading open ${requestLabelPlural}...`
          : openPullRequests.length === 0
            ? `No open ${requestLabelPlural} found`
            : `Select ${requestLabel} title`,
      disabled: true,
    },
    ...openPullRequests.map((pr) => ({ value: String(pr.number), label: pr.title })),
  ];
  const livePickerDisabled = !selectedRepo || prsLoading || prsError || openPullRequests.length === 0;
  const canSubmit = !!selectedRepo && (manualEntry ? !!prNumber && !!title : !!selectedOpenPullRequest);

  function reset() {
    setSelectedRepo(null);
    setManualEntry(false);
    setPrNumber("");
    setTitle("");
    setAuthor("");
    setTargetBranch("");
  }

  function selectRepository(repositoryId: string) {
    const repo = (repos ?? []).find((item) => item.id === repositoryId) ?? null;
    setSelectedRepo(repo);
    setManualEntry(false);
    setPrNumber("");
    setTitle("");
    setAuthor("");
    setTargetBranch("");
  }

  function selectPullRequest(pr: RepoPullRequest, manual = false) {
    setPrNumber(String(pr.number));
    setTitle(pr.title);
    setAuthor(pr.author);
    setTargetBranch(pr.target_branch ?? "");
    setManualEntry(manual);
  }

  function selectPullRequestNumber(value: string) {
    const pr = openPullRequests.find((item) => String(item.number) === value);
    if (pr) selectPullRequest(pr);
  }

  const trigger = useMutation({
    mutationFn: () => {
      const selectedPrNumber = prNumber || (selectedOpenPullRequest ? String(selectedOpenPullRequest.number) : "");
      const selectedTitle = title || selectedOpenPullRequest?.title || "";
      const selectedAuthor = author || selectedOpenPullRequest?.author || "";
      const selectedTargetBranch = targetBranch || selectedOpenPullRequest?.target_branch || "";
      return api.post<PRReview>("/api/pr-reviews", {
        repository_id: selectedRepo!.id,
        pr_number: Number(selectedPrNumber),
        title: selectedTitle,
        ...(selectedAuthor ? { author: selectedAuthor } : {}),
        ...(selectedTargetBranch ? { target_branch: selectedTargetBranch } : {}),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pr-reviews"] });
      onClose();
      reset();
      toast.success("Review queued — running a real scan now");
    },
  });

  return (
    <Modal
      open={open}
      onClose={() => {
        onClose();
        reset();
      }}
      title="Review a pull request"
      description="Select a repository, then choose an open pull request from the PR number and PR title listboxes."
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          trigger.mutate();
        }}
      >
        <Field label="Repository">
          <Select value={selectedRepoId} onChange={selectRepository} options={providerOptions} disabled={!reposLoaded || (repos?.length ?? 0) === 0} className="w-full" />
        </Field>
        {!manualEntry && (
          <>
            <Field label="PR number">
              <Select
                value={selectedOpenPullRequest ? String(selectedOpenPullRequest.number) : ""}
                onChange={selectPullRequestNumber}
                options={pullRequestOptions}
                disabled={livePickerDisabled}
                className="w-full"
              />
            </Field>
            <Field label="PR title">
              <Select
                value={selectedOpenPullRequest ? String(selectedOpenPullRequest.number) : ""}
                onChange={selectPullRequestNumber}
                options={pullRequestTitleOptions}
                disabled={livePickerDisabled}
                className="w-full"
              />
            </Field>
          </>
        )}
        {manualEntry && (
          <>
            <Field label="PR number">
              <TextInput type="number" required value={prNumber} onChange={(e) => setPrNumber(e.target.value)} placeholder="42" />
            </Field>
            <Field label="PR title">
              <TextInput required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add wallet withdraw endpoint" />
            </Field>
          </>
        )}
        {selectedOpenPullRequest && !manualEntry && (
          <div className="mb-4 flex items-center gap-2 rounded-lg border border-[#222] px-3 py-2 text-xs text-[#888]">
            <GitPullRequest size={14} />
            <span className="min-w-0 truncate">
              by {selectedOpenPullRequest.author}
              {selectedOpenPullRequest.target_branch ? ` · target ${selectedOpenPullRequest.target_branch}` : ""}
            </span>
          </div>
        )}
        {prsError && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
            <p>{pullRequestFetchErrorMessage(pullRequestsError)}</p>
            <div className="mt-3 flex gap-2">
              <Button type="button" variant="secondary" onClick={() => refetchPullRequests()}>
                Retry
              </Button>
              <Button type="button" variant="secondary" onClick={() => setManualEntry(true)}>
                Enter manually
              </Button>
            </div>
          </div>
        )}
        {selectedRepo && !manualEntry && !prsLoading && !prsError && (
          <button type="button" onClick={() => setManualEntry(true)} className="mb-4 -mt-2 text-xs text-[#888] hover:text-white">
            Can't find it? Enter the {requestLabel} number manually
          </button>
        )}
        {manualEntry && !!pullRequests?.length && (
          <button type="button" onClick={() => setManualEntry(false)} className="mb-4 -mt-2 text-xs text-[#888] hover:text-white">
            Pick from open {requestLabelPlural} instead
          </button>
        )}
        <Button type="submit" className="w-full" disabled={trigger.isPending || !canSubmit}>
          {trigger.isPending ? "Reviewing…" : "Run review"}
        </Button>
      </form>
    </Modal>
  );
}
