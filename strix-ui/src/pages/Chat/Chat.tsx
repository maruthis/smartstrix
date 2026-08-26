import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Check, Github, Gitlab, Paperclip, X } from "lucide-react";
import { api } from "../../api/client";
import type { ChatMessage, ChatSession, ChatSuggestion, Repository } from "../../api/types";
import { Modal } from "../../components/shared/Modal";
import { TextInput } from "../../components/shared/Form";
import { cn } from "../../lib/cn";

const CATEGORY_LABELS: Record<string, string> = {
  web: "Web",
  code: "Code",
  cloud: "Cloud",
  recon: "Recon",
  network: "Network",
  threat_intel: "Threat Intel",
  compliance: "Compliance",
};

export default function Chat() {
  const [category, setCategory] = useState("web");
  const [session, setSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [selectedRepos, setSelectedRepos] = useState<Repository[]>([]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [failedPrompt, setFailedPrompt] = useState<string | null>(null);
  const creatingSession = useRef<Promise<ChatSession> | null>(null);
  const queryClient = useQueryClient();

  const { data: suggestionsData } = useQuery({
    queryKey: ["chat-suggestions"],
    queryFn: () => api.get<{ categories: string[]; suggestions: Record<string, ChatSuggestion[]> }>("/api/chat/suggestions"),
  });

  const createSession = useMutation({
    mutationFn: (cat: string) => api.post<ChatSession>("/api/chat/sessions", { category: cat }),
  });

  const { data: sessionsData } = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: () => api.get<ChatSession[]>("/api/chat/sessions"),
  });

  const loadSession = useMutation({
    mutationFn: async (next: ChatSession) => ({
      session: next,
      messages: await api.get<ChatMessage[]>(`/api/chat/sessions/${next.id}/messages`),
    }),
    onSuccess: (loaded) => {
      setSession(loaded.session);
      setMessages(Array.isArray(loaded.messages) ? loaded.messages : []);
      setFailedPrompt(null);
    },
  });

  const sendMessage = useMutation({
    mutationFn: async (content: string) => {
      let currentSession = session;
      if (!currentSession) {
        if (!creatingSession.current) {
          creatingSession.current = createSession.mutateAsync(category).finally(() => {
            creatingSession.current = null;
          });
        }
        currentSession = await creatingSession.current;
        setSession(currentSession);
        queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
      }
      return api.post<ChatMessage[]>(`/api/chat/sessions/${currentSession.id}/messages`, {
        content,
        repository_ids: selectedRepos.map((r) => r.id),
      });
    },
    onSuccess: (newMessages) => {
      setMessages((prev) => [...prev, ...newMessages]);
      setInput("");
      setFailedPrompt(null);
    },
    onError: (_error, content) => {
      setFailedPrompt(content);
    },
  });

  function submit(content: string) {
    if (!content.trim() || sendMessage.isPending) return;
    sendMessage.mutate(content);
  }

  const suggestions = suggestionsData?.suggestions[category] ?? [];
  const sessions = Array.isArray(sessionsData) ? sessionsData : [];
  const errorMessage = sendMessage.error || loadSession.error || createSession.error
    ? sendMessage.error instanceof Error
      ? sendMessage.error.message
      : loadSession.error instanceof Error
        ? loadSession.error.message
        : createSession.error instanceof Error
          ? createSession.error.message
          : "Something went wrong"
    : null;

  const repoPicker = (
    <>
      <RepoChips repos={selectedRepos} onRemove={(id) => setSelectedRepos((prev) => prev.filter((r) => r.id !== id))} />
      <RepoPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        selected={selectedRepos}
        onToggle={(repo) =>
          setSelectedRepos((prev) => (prev.some((r) => r.id === repo.id) ? prev.filter((r) => r.id !== repo.id) : [...prev, repo]))
        }
      />
    </>
  );

  if (session || messages.length > 0) {
    return (
      <div className="mx-auto flex h-full max-w-3xl flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto pb-4">
          {messages.map((m) => (
            <div
              key={m.id}
              className={cn(
                "max-w-[85%] whitespace-pre-wrap rounded-xl px-4 py-2.5 text-sm",
                m.role === "user" ? "ml-auto bg-white text-black" : "bg-[rgba(255,255,255,0.05)] text-white"
              )}
            >
              {m.content}
            </div>
          ))}
          {sendMessage.isPending && <div className="text-xs text-[#666]">Strix is thinking…</div>}
        </div>
        {errorMessage && (
          <div className="mb-3 rounded-lg border border-red-900/50 bg-red-950/20 px-3 py-2 text-sm text-red-200">
            <div>{errorMessage}</div>
            {failedPrompt && (
              <button type="button" onClick={() => submit(failedPrompt)} className="mt-1 text-xs text-red-100 underline">
                Retry last message
              </button>
            )}
          </div>
        )}
        {repoPicker}
        <ChatInput value={input} onChange={setInput} onSubmit={submit} busy={sendMessage.isPending} onAddRepositories={() => setPickerOpen(true)} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center">
      <h1 className="mb-6 text-2xl font-semibold text-white">What do you want to secure today?</h1>
      <div className="w-full">
        {repoPicker}
        <ChatInput value={input} onChange={setInput} onSubmit={submit} busy={sendMessage.isPending} onAddRepositories={() => setPickerOpen(true)} />
      </div>

      <div className="mt-6 flex flex-wrap justify-center gap-1.5">
        {Object.keys(CATEGORY_LABELS).map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm transition-colors",
              category === cat ? "border-white bg-white text-black" : "border-[#2a2a2a] text-[#aaa] hover:text-white"
            )}
          >
            {CATEGORY_LABELS[cat]}
          </button>
        ))}
      </div>

      <div className="mt-6 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {suggestions.map((s) => (
          <button
            key={s.title}
            onClick={() => submit(s.prompt)}
            className="rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-4 text-left hover:border-[#333]"
          >
            <div className="mb-1 text-sm font-medium text-white">{s.title}</div>
            <div className="text-xs text-[#888]">{s.prompt}</div>
          </button>
        ))}
      </div>

      {sessions.length > 0 && (
        <div className="mt-6 w-full">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-[#666]">Recent conversations</div>
          <div className="space-y-1.5">
            {sessions.slice(0, 5).map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => loadSession.mutate(item)}
                className="flex w-full items-center justify-between rounded-lg border border-[#222] px-3 py-2 text-left text-sm text-[#ccc] hover:border-[#333] hover:text-white"
              >
                <span className="truncate">{item.title}</span>
                <span className="ml-3 shrink-0 text-xs text-[#666]">{CATEGORY_LABELS[item.category] ?? item.category}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function RepoChips({ repos, onRemove }: { repos: Repository[]; onRemove: (id: string) => void }) {
  if (repos.length === 0) return null;
  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {repos.map((r) => (
        <span key={r.id} className="flex items-center gap-1.5 rounded-full border border-[#2a2a2a] bg-[rgba(255,255,255,0.03)] px-2.5 py-1 text-xs text-[#ccc]">
          {r.provider === "gitlab" ? <Gitlab size={11} /> : <Github size={11} />}
          {r.full_name}
          <button type="button" onClick={() => onRemove(r.id)} className="text-[#666] hover:text-white">
            <X size={11} />
          </button>
        </span>
      ))}
    </div>
  );
}

function RepoPickerModal({
  open,
  onClose,
  selected,
  onToggle,
}: {
  open: boolean;
  onClose: () => void;
  selected: Repository[];
  onToggle: (repo: Repository) => void;
}) {
  const [search, setSearch] = useState("");
  const { data: repos, isLoading } = useQuery({
    queryKey: ["repositories"],
    queryFn: () => api.get<Repository[]>("/api/repositories"),
    enabled: open,
  });

  const filtered = (repos ?? []).filter((r) => r.full_name.toLowerCase().includes(search.toLowerCase()));
  const selectedIds = new Set(selected.map((r) => r.id));

  return (
    <Modal open={open} onClose={onClose} title="Add repositories" description="Pick which connected repositories Strix should scan for this request.">
      <TextInput autoFocus value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search repositories" className="mb-3" />
      <div className="max-h-72 space-y-1.5 overflow-y-auto">
        {!isLoading && (repos?.length ?? 0) === 0 && (
          <p className="py-6 text-center text-sm text-[#666]">No connected repositories yet — add one from the Repositories page.</p>
        )}
        {!isLoading && (repos?.length ?? 0) > 0 && filtered.length === 0 && (
          <p className="py-6 text-center text-sm text-[#666]">No repositories match "{search}".</p>
        )}
        {filtered.map((repo) => {
          const isSelected = selectedIds.has(repo.id);
          return (
            <button
              key={repo.id}
              type="button"
              onClick={() => onToggle(repo)}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-sm hover:bg-[rgba(255,255,255,0.04)]",
                isSelected ? "border-white/40 text-white" : "border-[#222] text-white"
              )}
            >
              {repo.provider === "gitlab" ? <Gitlab size={15} className="shrink-0 text-[#888]" /> : <Github size={15} className="shrink-0 text-[#888]" />}
              <span className="flex-1 break-all">{repo.full_name}</span>
              {isSelected && <Check size={15} className="shrink-0 text-white" />}
            </button>
          );
        })}
      </div>
      <button type="button" onClick={onClose} className="mt-4 w-full rounded-lg bg-white py-2 text-sm font-medium text-black hover:bg-white/90">
        Done{selected.length > 0 ? ` (${selected.length} selected)` : ""}
      </button>
    </Modal>
  );
}

function ChatInput({
  value,
  onChange,
  onSubmit,
  busy,
  onAddRepositories,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (v: string) => void;
  busy: boolean;
  onAddRepositories: () => void;
}) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(value);
      }}
      className="rounded-xl border border-[#2a2a2a] bg-[rgba(255,255,255,0.02)] p-3"
    >
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSubmit(value);
          }
        }}
        rows={2}
        placeholder="Tell Strix what to do…"
        className="w-full resize-none bg-transparent text-sm text-white outline-none placeholder:text-[#555]"
      />
      <div className="mt-2 flex items-center justify-between">
        <button
          type="button"
          onClick={onAddRepositories}
          className="flex items-center gap-1.5 rounded-lg border border-[#2a2a2a] px-2.5 py-1.5 text-xs text-[#888] hover:text-white"
        >
          <Paperclip size={13} /> Add repositories
        </button>
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-black disabled:opacity-40"
        >
          <ArrowUp size={15} />
        </button>
      </div>
    </form>
  );
}
