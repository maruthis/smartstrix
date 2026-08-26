import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search, CalendarClock, GitPullRequest } from "lucide-react";
import { Button } from "../../components/shared/Form";
import { api } from "../../api/client";
import type { IssuesResponse, Pentest, PRReviewsResponse } from "../../api/types";

const CARDS = [
  {
    icon: Search,
    title: "Run your first pentest",
    description: "Find vulnerabilities in your apps and APIs with a security test.",
    cta: "Start Pentest",
    to: "/pentests",
  },
  {
    icon: CalendarClock,
    title: "Schedule pentests",
    description: "Automate recurring security tests on your own schedule.",
    cta: "Set Up Schedule",
    to: "/pentests",
  },
  {
    icon: GitPullRequest,
    title: "Enable PR reviews",
    description: "Catch vulnerabilities in every PR with checks that block risky merges.",
    cta: "Enable Reviews",
    to: "/pr-reviews",
  },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const { data: pentests } = useQuery({ queryKey: ["pentests"], queryFn: () => api.get<Pentest[]>("/api/pentests") });
  const { data: issues } = useQuery({ queryKey: ["issues", "open", "", ""], queryFn: () => api.get<IssuesResponse>("/api/issues?status_filter=open") });
  const { data: reviews } = useQuery({ queryKey: ["pr-reviews", "all", ""], queryFn: () => api.get<PRReviewsResponse>("/api/pr-reviews") });

  const runningPentests = (pentests ?? []).filter((p) => p.status === "queued" || p.status === "running").length;
  const openCritical = issues?.severity_counts?.critical ?? 0;
  const openHigh = issues?.severity_counts?.high ?? 0;
  const activeReviews = (reviews?.items ?? []).filter((r) => r.status === "running").length;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-white">Dashboard</h1>
        <p className="mt-1 text-sm text-[#888]">Current scan activity and open security decisions.</p>
      </div>

      <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <Metric label="Open critical" value={openCritical} tone={openCritical > 0 ? "danger" : "neutral"} />
        <Metric label="Open high" value={openHigh} tone={openHigh > 0 ? "warning" : "neutral"} />
        <Metric label="Running pentests" value={runningPentests} />
        <Metric label="Running PR reviews" value={activeReviews} />
      </div>

      <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {CARDS.map((card) => (
          <div key={card.title} className="flex flex-col items-center rounded-xl border border-[#222] bg-[rgba(255,255,255,0.02)] p-6">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl border border-[#2a2a2a]">
              <card.icon size={20} className="text-white" />
            </div>
            <h3 className="mb-1.5 font-semibold text-white">{card.title}</h3>
            <p className="mb-5 flex-1 text-sm text-[#888]">{card.description}</p>
            <Button className="w-full" onClick={() => navigate(card.to)}>
              {card.cta}
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

function Metric({ label, value, tone = "neutral" }: { label: string; value: number; tone?: "neutral" | "warning" | "danger" }) {
  const valueClass = tone === "danger" ? "text-red-300" : tone === "warning" ? "text-amber-300" : "text-white";
  return (
    <div
      className="rounded-lg border border-[#222] bg-[rgba(255,255,255,0.02)] p-4 text-left"
      aria-label={`${label}: ${value}`}
    >
      <div className="text-xs uppercase tracking-wide text-[#666]">{label}</div>
      <div className={`mt-2 text-3xl font-semibold ${valueClass}`}>{value}</div>
    </div>
  );
}
