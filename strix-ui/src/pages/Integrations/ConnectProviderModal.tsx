import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { Integration } from "../../api/types";
import { Modal } from "../../components/shared/Modal";
import { Button, Field, TextInput } from "../../components/shared/Form";
import { toast } from "../../components/shared/Toast";

const ACCOUNT_LABEL_HINT: Record<string, string> = {
  github: "GitHub organization or username",
  gitlab: "GitLab group or username",
  bitbucket: "Bitbucket workspace",
  slack: "Slack workspace",
  jira: "Jira site (e.g. acme.atlassian.net)",
  linear: "Linear workspace",
};

const BASE_URL_HINT: Record<string, string> = {
  github: "https://github.example.com (leave blank for github.com, or GitHub Enterprise Server)",
  gitlab: "https://gitlab.example.com (leave blank for gitlab.com)",
};

export function ConnectProviderModal({
  integration,
  onClose,
}: {
  integration: Integration | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [accountLabel, setAccountLabel] = useState("");
  const [credential, setCredential] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  function reset() {
    setAccountLabel("");
    setCredential("");
    setBaseUrl("");
  }

  const connect = useMutation({
    mutationFn: () =>
      api.post<Integration>(`/api/integrations/${integration!.provider}/connect`, {
        account_label: accountLabel,
        credential: credential || undefined,
        base_url: baseUrl || undefined,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData<Integration[]>(["integrations"], (prev) => prev?.map((i) => (i.provider === updated.provider ? updated : i)));
      toast.success(`${updated.label} connected`);
      reset();
      onClose();
    },
  });

  if (!integration) return null;

  const credentialRequired = integration.live;

  return (
    <Modal
      open={!!integration}
      onClose={() => {
        reset();
        onClose();
      }}
      title={`Connect ${integration.label}`}
      description={
        integration.live
          ? `Strix verifies this token against ${integration.label} right away — nothing is saved unless it works.`
          : `Provide the account and credentials Strix should use to connect to ${integration.label}.`
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          connect.mutate();
        }}
      >
        <Field label={ACCOUNT_LABEL_HINT[integration.provider] ?? "Account name"}>
          <TextInput
            autoFocus
            required
            value={accountLabel}
            onChange={(e) => setAccountLabel(e.target.value)}
            placeholder="e.g. acme-corp"
          />
        </Field>
        <Field label={credentialRequired ? "Personal access token" : "Personal access token (optional)"}>
          <TextInput
            type="password"
            required={credentialRequired}
            value={credential}
            onChange={(e) => setCredential(e.target.value)}
            placeholder="Paste a token to authenticate as this account"
          />
        </Field>
        {integration.live && (
          <Field label="Instance URL (optional)">
            <TextInput value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={BASE_URL_HINT[integration.provider]} />
          </Field>
        )}
        <p className="mb-4 text-xs text-[#666]">
          {integration.live
            ? "Tokens are encrypted at rest, never stored in full plaintext — only the last 4 characters are kept for display."
            : "Tokens are never stored in full — only the last 4 characters are kept, for display purposes."}
        </p>
        <Button
          type="submit"
          className="w-full"
          disabled={!accountLabel.trim() || (credentialRequired && !credential.trim()) || connect.isPending}
        >
          {connect.isPending ? "Connecting…" : `Connect ${integration.label}`}
        </Button>
      </form>
    </Modal>
  );
}
