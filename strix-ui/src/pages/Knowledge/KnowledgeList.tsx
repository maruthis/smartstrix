import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Plus, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import type { KnowledgeEntry, Repository, DomainOut } from "../../api/types";
import { EmptyState } from "../../components/shared/EmptyState";
import { Modal } from "../../components/shared/Modal";
import { FilterBar } from "../../components/shared/FilterBar";
import { Button, Field, Select, TextArea } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";
import { useDebouncedValue } from "../../lib/useDebouncedValue";

export default function KnowledgeList() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebouncedValue(search, 300);

  const { data: entries, isLoading } = useQuery({
    queryKey: ["knowledge", debouncedSearch],
    queryFn: () => api.get<KnowledgeEntry[]>(`/api/knowledge${debouncedSearch ? `?search=${encodeURIComponent(debouncedSearch)}` : ""}`),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/api/knowledge/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      toast.success("Knowledge entry removed");
    },
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Knowledge &amp; Context</h1>
          <p className="mt-1 text-sm text-[#888]">Strix learns your apps, context, and business logic across runs to deliver smarter results.</p>
        </div>
        <Button onClick={() => setAddOpen(true)}>
          <Plus size={15} /> Add Knowledge
        </Button>
      </div>

      <FilterBar search={search} onSearch={setSearch} placeholder="Search knowledge" />

      {!isLoading && entries?.length === 0 && <EmptyState icon={<Database size={20} />} title="No custom context added" />}

      {entries && entries.length > 0 && (
        <div className="space-y-2">
          {entries.map((entry) => (
            <div key={entry.id} className="flex items-start justify-between rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-4">
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <span className="rounded-full border border-[#2a2a2a] px-2 py-0.5 text-xs capitalize text-[#aaa]">
                    {entry.type.replace(/_/g, " ")}
                  </span>
                  <span className="text-xs text-[#666] capitalize">{entry.scope_type}</span>
                </div>
                <p className="whitespace-pre-wrap text-sm text-[#ccc]">{entry.description}</p>
              </div>
              <button onClick={() => remove.mutate(entry.id)} className="text-[#666] hover:text-red-400">
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}

      <AddKnowledgeModal open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}

function AddKnowledgeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { data: repos } = useQuery({ queryKey: ["repositories"], queryFn: () => api.get<Repository[]>("/api/repositories"), enabled: open });
  const { data: domains } = useQuery({ queryKey: ["domains"], queryFn: () => api.get<DomainOut[]>("/api/domains"), enabled: open });

  const [type, setType] = useState("business_logic");
  const [description, setDescription] = useState("");
  const [scopeType, setScopeType] = useState<"global" | "repository" | "domain">("global");
  const [scopeId, setScopeId] = useState("");

  const add = useMutation({
    mutationFn: () =>
      api.post("/api/knowledge", {
        type,
        description,
        scope_type: scopeType,
        scope_id: scopeType === "global" ? null : scopeId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      setDescription("");
      onClose();
      toast.success("Knowledge added");
    },
  });

  const scopeOptions = scopeType === "repository" ? repos ?? [] : scopeType === "domain" ? domains ?? [] : [];

  return (
    <Modal open={open} onClose={onClose} title="Add Knowledge">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <Field label="Type">
          <Select
            value={type}
            onChange={setType}
            options={[
              { value: "business_logic", label: "Business Logic" },
              { value: "architecture", label: "Architecture" },
              { value: "auth_model", label: "Auth Model" },
              { value: "other", label: "Other" },
            ]}
            className="w-full"
          />
        </Field>
        <Field label="Description">
          <TextArea required rows={5} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Describe the business logic, constraint, or context Strix should know…" />
        </Field>
        <Field label="Scope">
          <Select
            value={scopeType}
            onChange={(v) => {
              setScopeType(v as typeof scopeType);
              setScopeId("");
            }}
            options={[
              { value: "global", label: "Applies globally" },
              { value: "repository", label: "Specific repository" },
              { value: "domain", label: "Specific domain" },
            ]}
            className="w-full"
          />
        </Field>
        {scopeType !== "global" && (
          <Field label={scopeType === "repository" ? "Repository" : "Domain"}>
            <Select
              value={scopeId}
              onChange={setScopeId}
              options={[
                { value: "", label: "Select…" },
                ...scopeOptions.map((o) => ({ value: o.id, label: "full_name" in o ? o.full_name : o.hostname })),
              ]}
              className="w-full"
            />
          </Field>
        )}
        <Button type="submit" className="w-full" disabled={!description.trim() || add.isPending || (scopeType !== "global" && !scopeId)}>
          {add.isPending ? "Adding…" : "Add Knowledge"}
        </Button>
      </form>
    </Modal>
  );
}
