import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Github, Gitlab, Layers, Plus } from "lucide-react";
import { api } from "../../api/client";
import type { Repository } from "../../api/types";
import { EmptyState } from "../../components/shared/EmptyState";
import { AddRepositoryModal } from "../../components/shared/AddRepositoryModal";
import { StatusPill } from "../../components/shared/StatusPill";
import { Button, Toggle } from "../../components/shared/Form";
import { timeAgo } from "../../lib/format";

export default function RepositoriesList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: repos, isLoading } = useQuery({
    queryKey: ["repositories"],
    queryFn: () => api.get<Repository[]>("/api/repositories"),
  });

  const toggleAutoReview = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      api.patch(`/api/repositories/${id}`, { auto_review_enabled: enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["repositories"] }),
  });

  const scan = useMutation({
    mutationFn: (id: string) => api.post<{ pentest_id: string }>(`/api/repositories/${id}/scan`),
    onSuccess: (res) => navigate(`/pentests/${res.pentest_id}`),
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Repositories</h1>
        <Button onClick={() => setAddOpen(true)}>
          <Plus size={15} /> Add Repository
        </Button>
      </div>

      {!isLoading && repos?.length === 0 && (
        <EmptyState icon={<Layers size={20} />} title="No repositories yet" description="Connect a repository to start scanning it." />
      )}

      {repos && repos.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-[#222]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#222] text-left text-xs uppercase tracking-wide text-[#666]">
                <th className="px-4 py-3 font-medium">Repository</th>
                <th className="px-4 py-3 font-medium">Issues</th>
                <th className="px-4 py-3 font-medium">Auto-Review</th>
                <th className="px-4 py-3 font-medium">Last Tested</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {repos.map((repo) => (
                <tr key={repo.id} className="border-b border-[#1a1a1a] last:border-0 hover:bg-[rgba(255,255,255,0.02)]">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 text-white">
                      {repo.provider === "gitlab" ? <Gitlab size={15} className="text-[#888]" /> : <Github size={15} className="text-[#888]" />}
                      {repo.full_name}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[#aaa]">{repo.open_issues_count || "—"}</td>
                  <td className="min-w-[150px] px-4 py-3">
                    <div className="flex flex-nowrap items-center gap-2.5">
                      <Toggle
                        checked={repo.auto_review_enabled}
                        onChange={(v) => toggleAutoReview.mutate({ id: repo.id, enabled: v })}
                      />
                      <span className="shrink-0 whitespace-nowrap">
                        <StatusPill value={repo.auto_review_enabled ? "enabled" : "disabled"} />
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[#aaa]">{repo.last_tested_at ? timeAgo(repo.last_tested_at) : "—"}</td>
                  <td className="px-4 py-3">
                    <Button variant="secondary" onClick={() => scan.mutate(repo.id)} disabled={scan.isPending}>
                      Run scan
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddRepositoryModal open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}
