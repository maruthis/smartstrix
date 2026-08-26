import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScrollText } from "lucide-react";
import { api } from "../../api/client";
import type { AuditLogEntry, MembershipOut, PaginatedResponse, RequestLogEntry } from "../../api/types";
import { EmptyState } from "../../components/shared/EmptyState";
import { FilterBar, Tabs } from "../../components/shared/FilterBar";
import { ListSelect } from "../../components/shared/ListSelect";
import { Pagination } from "../../components/shared/Pagination";
import { formatDate } from "../../lib/format";

const PAGE_SIZE = 50;

type LogTab = "audit" | "requests";

export default function AuditLogsSettings() {
  const [tab, setTab] = useState<LogTab>("audit");

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold text-white">Logs & Audit</h1>
      <p className="mb-6 text-sm text-[#888]">A record of actions taken and API activity across this organization.</p>

      <Tabs
        tabs={[
          { key: "audit", label: "Audit Log" },
          { key: "requests", label: "Request Log" },
        ]}
        active={tab}
        onChange={(key) => setTab(key as LogTab)}
      />

      {tab === "audit" ? <AuditLogTab /> : <RequestLogTab />}
    </div>
  );
}

function humanizeAction(action: string): string {
  return action.replace(/\./g, " ").replace(/_/g, " ");
}

function llmUsageLabel(extra: Record<string, unknown>): string | null {
  const usage = extra.llm_usage;
  if (!usage || typeof usage !== "object") return null;
  const values = usage as Record<string, unknown>;
  const total = Number(values.total_tokens ?? 0);
  const input = Number(values.input_tokens ?? 0);
  const output = Number(values.output_tokens ?? 0);
  if (!Number.isFinite(total) || total <= 0) return null;
  return `${total.toLocaleString()} tokens (${Math.max(0, input).toLocaleString()} request + ${Math.max(0, output).toLocaleString()} response)`;
}

function AuditLogTab() {
  const [page, setPage] = useState(1);
  const [actorUserId, setActorUserId] = useState("");
  const [action, setAction] = useState("");

  const { data: members } = useQuery({ queryKey: ["members"], queryFn: () => api.get<MembershipOut[]>("/api/members") });

  const { data, isLoading } = useQuery({
    queryKey: ["audit-logs", page, actorUserId, action],
    queryFn: () =>
      api.get<PaginatedResponse<AuditLogEntry>>(
        `/api/settings/audit-logs?page=${page}&page_size=${PAGE_SIZE}` +
          (actorUserId ? `&actor_user_id=${encodeURIComponent(actorUserId)}` : "") +
          (action ? `&action=${encodeURIComponent(action)}` : "")
      ),
  });

  const entries = data?.items ?? [];

  return (
    <div>
      <FilterBar
        search={action}
        onSearch={(v) => {
          setAction(v);
          setPage(1);
        }}
        placeholder="Filter by action..."
      >
        <ListSelect
          value={actorUserId}
          onChange={(v) => {
            setActorUserId(v);
            setPage(1);
          }}
          ariaLabel="Filter by actor"
          options={[
            { value: "", label: "All members" },
            ...(members ?? []).map((m) => ({ value: m.user.id, label: m.user.email })),
          ]}
        />
      </FilterBar>

      {!isLoading && entries.length === 0 && <EmptyState icon={<ScrollText size={20} />} title="No activity yet" />}

      {entries.length > 0 && (
        <div className="space-y-1">
          {entries.map((e) => {
            const tokens = llmUsageLabel(e.extra);
            return (
              <div key={e.id} className="flex items-center justify-between gap-4 border-b border-[#1a1a1a] py-2.5 text-sm">
                <div className="min-w-0">
                  <div>
                    <span className="text-white">{e.actor_email}</span>{" "}
                    <span className="text-[#888]">{humanizeAction(e.action)}</span> <span className="text-[#aaa]">{e.target}</span>
                  </div>
                  {tokens && <div className="mt-0.5 font-mono text-xs text-[#666]">{tokens}</div>}
                </div>
                <span className="shrink-0 text-xs text-[#555]">{formatDate(e.created_at)}</span>
              </div>
            );
          })}
        </div>
      )}

      {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />}
    </div>
  );
}

const METHOD_COLORS: Record<string, string> = {
  POST: "text-emerald-400",
  PATCH: "text-blue-400",
  PUT: "text-blue-400",
  DELETE: "text-red-400",
  GET: "text-[#888]",
};

function RequestLogTab() {
  const [page, setPage] = useState(1);
  const [method, setMethod] = useState("");
  const [minStatus, setMinStatus] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["request-logs", page, method, minStatus],
    queryFn: () =>
      api.get<PaginatedResponse<RequestLogEntry>>(
        `/api/settings/request-logs?page=${page}&page_size=${PAGE_SIZE}` +
          (method ? `&method=${method}` : "") +
          (minStatus ? `&min_status=${minStatus}` : "")
      ),
  });

  const entries = data?.items ?? [];

  return (
    <div>
      <FilterBar>
        <ListSelect
          value={method}
          onChange={(v) => {
            setMethod(v);
            setPage(1);
          }}
          ariaLabel="Filter by method"
          options={[
            { value: "", label: "All methods" },
            { value: "POST", label: "POST" },
            { value: "PATCH", label: "PATCH" },
            { value: "PUT", label: "PUT" },
            { value: "DELETE", label: "DELETE" },
            { value: "GET", label: "GET (errors only)" },
          ]}
        />
        <ListSelect
          value={minStatus}
          onChange={(v) => {
            setMinStatus(v);
            setPage(1);
          }}
          ariaLabel="Filter by status"
          options={[
            { value: "", label: "Any status" },
            { value: "400", label: "4xx / 5xx (errors)" },
            { value: "500", label: "5xx only" },
          ]}
        />
      </FilterBar>

      {!isLoading && entries.length === 0 && (
        <EmptyState icon={<ScrollText size={20} />} title="No request activity yet" description="Mutating requests and errors will appear here." />
      )}

      {entries.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-[#222]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#222] text-left text-xs uppercase tracking-wide text-[#666]">
                <th className="px-4 py-3 font-medium">Actor</th>
                <th className="px-4 py-3 font-medium">Method</th>
                <th className="px-4 py-3 font-medium">Path</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Duration</th>
                <th className="px-4 py-3 font-medium">Time</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-b border-[#1a1a1a] last:border-0">
                  <td className="px-4 py-2.5 text-white">{e.actor_email}</td>
                  <td className={`px-4 py-2.5 font-mono text-xs font-semibold ${METHOD_COLORS[e.method] ?? "text-[#888]"}`}>{e.method}</td>
                  <td className="px-4 py-2.5 font-mono text-xs text-[#aaa]">{e.path}</td>
                  <td className={`px-4 py-2.5 ${e.status_code >= 400 ? "text-red-400" : "text-[#aaa]"}`}>{e.status_code}</td>
                  <td className="px-4 py-2.5 text-[#666]">{e.duration_ms}ms</td>
                  <td className="px-4 py-2.5 text-xs text-[#555]">{formatDate(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && <Pagination page={data.page} pageSize={data.page_size} total={data.total} onChange={setPage} />}
    </div>
  );
}
