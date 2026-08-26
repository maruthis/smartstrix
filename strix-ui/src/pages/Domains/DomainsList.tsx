import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Globe, Plus, ShieldCheck } from "lucide-react";
import { api } from "../../api/client";
import type { DomainOut } from "../../api/types";
import { EmptyState } from "../../components/shared/EmptyState";
import { Modal } from "../../components/shared/Modal";
import { StatusPill } from "../../components/shared/StatusPill";
import { Button, Field, TextInput } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";
import { timeAgo } from "../../lib/format";
import { hostnameFromInput } from "../../lib/hostname";

export default function DomainsList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: domains, isLoading } = useQuery({
    queryKey: ["domains"],
    queryFn: () => api.get<DomainOut[]>("/api/domains"),
  });

  const verify = useMutation({
    mutationFn: (id: string) => api.post(`/api/domains/${id}/verify`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      toast.success("Domain verified");
    },
  });

  const scan = useMutation({
    mutationFn: (id: string) => api.post<{ pentest_id: string }>(`/api/domains/${id}/scan`),
    onSuccess: (res) => navigate(`/pentests/${res.pentest_id}`),
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Domains &amp; APIs</h1>
        <Button onClick={() => setAddOpen(true)}>
          <Plus size={15} /> Add Domain
        </Button>
      </div>

      {!isLoading && domains?.length === 0 && (
        <EmptyState icon={<Globe size={20} />} title="No domains" description="Add your first domain to get started." />
      )}

      {domains && domains.length > 0 && (
        <div className="space-y-2">
          {domains.map((d) => (
            <Link
              key={d.id}
              to={`/domains/${d.id}`}
              className="flex items-center justify-between rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-4 hover:border-[#333]"
            >
              <div>
                <div className="flex items-center gap-2 text-white">
                  <Globe size={15} className="text-[#888]" />
                  {d.hostname}
                  <StatusPill value={d.verified ? "verified" : "queued"} label={d.verified ? "Verified" : "Unverified"} />
                </div>
                <div className="mt-1 text-xs text-[#666]">
                  {d.last_tested_at ? `Last tested ${timeAgo(d.last_tested_at)}` : "Never tested"}
                </div>
              </div>
              <div className="flex gap-2" onClick={(e) => e.preventDefault()}>
                {!d.verified && (
                  <Button variant="secondary" onClick={() => verify.mutate(d.id)} disabled={verify.isPending}>
                    <ShieldCheck size={14} /> Verify
                  </Button>
                )}
                {d.verified && (
                  <Button variant="secondary" onClick={() => scan.mutate(d.id)} disabled={scan.isPending}>
                    Run scan
                  </Button>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}

      <AddDomainModal open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}

function AddDomainModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [hostname, setHostname] = useState("");

  const add = useMutation({
    mutationFn: () => api.post<DomainOut>("/api/domains", { hostname: hostnameFromInput(hostname) }),
    onSuccess: (domain) => {
      queryClient.invalidateQueries({ queryKey: ["domains"] });
      setHostname("");
      onClose();
      toast.success(`Added ${domain.hostname}`);
    },
  });

  return (
    <Modal open={open} onClose={onClose} title="Add Domain" description="You'll need to verify ownership before scanning.">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <Field label="Hostname" hint="A hostname or a full URL — https://app.example.com/ is stored as app.example.com.">
          <TextInput required placeholder="app.example.com" value={hostname} onChange={(e) => setHostname(e.target.value)} autoFocus />
        </Field>
        <Button type="submit" className="w-full" disabled={add.isPending}>
          {add.isPending ? "Adding…" : "Add Domain"}
        </Button>
      </form>
    </Modal>
  );
}
