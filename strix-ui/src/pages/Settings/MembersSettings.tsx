import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus } from "lucide-react";
import { api } from "../../api/client";
import type { Invitation, MembershipOut } from "../../api/types";
import { Modal } from "../../components/shared/Modal";
import { Button, Field, Select, TextInput } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";

export default function MembersSettings() {
  const queryClient = useQueryClient();
  const [inviteOpen, setInviteOpen] = useState(false);

  const { data: members } = useQuery({ queryKey: ["members"], queryFn: () => api.get<MembershipOut[]>("/api/members") });
  const { data: invitations } = useQuery({ queryKey: ["invitations"], queryFn: () => api.get<Invitation[]>("/api/members/invitations") });

  const revoke = useMutation({
    mutationFn: (id: string) => api.post(`/api/members/invitations/${id}/revoke`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
      toast.success("Invitation revoked");
    },
  });

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Members</h1>
          <p className="mt-1 text-sm text-[#888]">Manage who has access to this organization</p>
        </div>
        <Button onClick={() => setInviteOpen(true)}>
          <UserPlus size={15} /> Invite Member
        </Button>
      </div>

      <div className="mb-6 rounded-xl border border-[#222]">
        <div className="border-b border-[#222] px-4 py-3 text-sm font-medium text-white">Team Members ({members?.length ?? 0})</div>
        {members?.map((m) => (
          <div key={m.id} className="flex items-center gap-3 border-b border-[#1a1a1a] px-4 py-3 last:border-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-700 text-xs font-semibold text-white">
              {m.user.name?.[0]}
            </div>
            <div>
              <div className="flex items-center gap-2 text-sm text-white">
                {m.user.name}
                <span className="rounded-full border border-[#2a2a2a] px-2 py-0.5 text-[10px] capitalize text-[#aaa]">{m.role}</span>
              </div>
              <div className="text-xs text-[#666]">{m.user.email}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-[#222]">
        <div className="border-b border-[#222] px-4 py-3 text-sm font-medium text-white">Pending Invitations ({invitations?.length ?? 0})</div>
        {invitations?.length === 0 && <div className="px-4 py-6 text-center text-sm text-[#666]">No pending invitations</div>}
        {invitations?.map((i) => (
          <div key={i.id} className="flex items-center justify-between border-b border-[#1a1a1a] px-4 py-3 last:border-0">
            <div>
              <div className="text-sm text-white">{i.email}</div>
              <div className="text-xs text-[#666] capitalize">{i.role}</div>
            </div>
            <Button variant="ghost" onClick={() => revoke.mutate(i.id)}>
              Revoke
            </Button>
          </div>
        ))}
      </div>

      <InviteModal open={inviteOpen} onClose={() => setInviteOpen(false)} />
    </div>
  );
}

function InviteModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");

  const invite = useMutation({
    mutationFn: () => api.post<{ dev_accept_token: string }>("/api/members/invitations", { email, role }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
      setEmail("");
      onClose();
      toast.success(`Invitation sent to ${email}`);
    },
  });

  return (
    <Modal open={open} onClose={onClose} title="Invite Member">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          invite.mutate();
        }}
      >
        <Field label="Email">
          <TextInput type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@company.com" />
        </Field>
        <Field label="Role">
          <Select
            value={role}
            onChange={setRole}
            options={[
              { value: "member", label: "Member" },
              { value: "admin", label: "Admin" },
            ]}
            className="w-full"
          />
        </Field>
        <Button type="submit" className="w-full" disabled={invite.isPending}>
          {invite.isPending ? "Sending…" : "Send Invitation"}
        </Button>
      </form>
    </Modal>
  );
}
