import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { useSession } from "../../store/session";
import { Button, Field, TextInput, Toggle } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";

export default function GeneralSettings() {
  const { me, refresh, logout } = useSession();
  const navigate = useNavigate();
  const [name, setName] = useState(me?.active_org?.name ?? "");
  const [confirmName, setConfirmName] = useState("");
  const isAdmin = me?.role === "admin";

  useEffect(() => {
    setName(me?.active_org?.name ?? "");
    setConfirmName("");
  }, [me?.active_org?.id, me?.active_org?.name]);

  const rename = useMutation({
    mutationFn: () => api.patch("/api/orgs/current", { name }),
    onSuccess: () => {
      refresh();
      toast.success("Organization renamed");
    },
  });

  const deleteOrg = useMutation({
    mutationFn: () => api.delete("/api/orgs/current"),
    onSuccess: async () => {
      await refresh();
      toast.success("Organization deleted");
      navigate("/onboarding");
    },
  });

  if (!me?.active_org) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">General</h1>

      <div className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-700 text-sm font-semibold text-white">
            {me.user.name?.[0]}
          </div>
          <div>
            <div className="text-sm font-medium text-white">{me.user.name}</div>
            <div className="text-xs text-[#666]">{me.user.email}</div>
          </div>
          <span className="ml-auto rounded-full border border-[#2a2a2a] px-2 py-0.5 text-xs text-[#aaa]">Pro</span>
        </div>
      </div>

      <div className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-white">Two-Factor Authentication</div>
            <div className="mt-0.5 text-xs text-[#888]">Protect your account with an authenticator app that generates one-time codes.</div>
          </div>
          <Toggle checked={me.user.two_factor_enabled} onChange={() => {}} disabled />
        </div>
      </div>

      <div className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-5">
        <h2 className="mb-3 text-sm font-medium text-white">Organization</h2>
        <Field label="Name">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} disabled={!isAdmin} />
        </Field>
        <Button onClick={() => rename.mutate()} disabled={!isAdmin || rename.isPending} variant="secondary">
          Save Changes
        </Button>
        <div className="mt-4 space-y-1 border-t border-[#1a1a1a] pt-4 text-xs text-[#888]">
          <div>
            Organization ID <span className="font-mono text-[#aaa]">{me.active_org.id}</span>
          </div>
          <div>Your Role {me.role}</div>
        </div>
      </div>

      {isAdmin && (
        <div className="rounded-xl border border-red-900/40 bg-red-950/10 p-5">
          <h2 className="mb-1 text-sm font-medium text-red-400">Danger Zone</h2>
          <p className="mb-3 text-xs text-[#888]">This action can not be undone. All data associated with this organization will be permanently deleted.</p>
          <TextInput
            placeholder={`Type "${me.active_org.name}" to confirm`}
            value={confirmName}
            onChange={(e) => setConfirmName(e.target.value)}
            className="mb-2"
          />
          <Button
            variant="danger"
            disabled={confirmName !== me.active_org.name || deleteOrg.isPending}
            onClick={() => deleteOrg.mutate()}
          >
            Delete Organization
          </Button>
        </div>
      )}

      <div className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-white">Sign Out</div>
            <div className="text-xs text-[#888]">Sign out of your account on this device.</div>
          </div>
          <Button variant="danger" onClick={() => logout()}>
            Sign Out
          </Button>
        </div>
      </div>
    </div>
  );
}
