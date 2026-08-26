import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { Subscription } from "../../api/types";
import { StatusPill } from "../../components/shared/StatusPill";
import { Button } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";
import { formatDate } from "../../lib/format";

export default function BillingSettings() {
  const queryClient = useQueryClient();
  const { data: sub } = useQuery({ queryKey: ["billing"], queryFn: () => api.get<Subscription>("/api/settings/billing") });

  const addCard = useMutation({
    mutationFn: () => api.post<Subscription>("/api/settings/billing/add-card"),
    onSuccess: (updated) => {
      queryClient.setQueryData(["billing"], updated);
      toast.success("Card added");
    },
  });

  if (!sub) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">Billing</h1>

      <div className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium capitalize text-white">{sub.plan.replace(/_/g, " ")}</div>
            <StatusPill value={sub.status} />
          </div>
          {!sub.card_added && (
            <Button onClick={() => addCard.mutate()} disabled={addCard.isPending}>
              Add card
            </Button>
          )}
        </div>
        {sub.trial_ends_at && sub.status === "trialing" && (
          <p className="mt-3 text-xs text-[#888]">Trial ends {formatDate(sub.trial_ends_at)}.</p>
        )}
      </div>

      <div className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-5">
        <h2 className="mb-2 text-sm font-medium text-white">Invoices</h2>
        <p className="text-sm text-[#666]">No invoices yet.</p>
      </div>
    </div>
  );
}
