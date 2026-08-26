import { NavLink } from "react-router-dom";
import {
  LayoutGrid,
  Search,
  AlertTriangle,
  GitPullRequest,
  MessageSquare,
  Layers,
  Globe,
  Share2,
  Database,
  Puzzle,
  Settings,
  ChevronDown,
  Lock,
} from "lucide-react";
import { useState } from "react";
import { useSession } from "../store/session";
import { cn } from "../lib/cn";

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutGrid },
  { to: "/pentests", label: "Pentests", icon: Search },
  { to: "/issues", label: "Issues", icon: AlertTriangle },
  { to: "/pr-reviews", label: "PR Reviews", icon: GitPullRequest },
  { to: "/chat", label: "Chat", icon: MessageSquare },
];

const NAV2 = [
  { to: "/repositories", label: "Repositories", icon: Layers },
  { to: "/domains", label: "Domains", icon: Globe },
  { to: "/networks", label: "Networks", icon: Share2, feature: "networks" },
  { to: "/knowledge", label: "Knowledge", icon: Database },
  { to: "/integrations", label: "Integrations", icon: Puzzle },
];

function NavItem({ to, label, icon: Icon, locked }: { to: string; label: string; icon: typeof LayoutGrid; locked?: boolean }) {
  if (locked) {
    return (
      <div className="flex cursor-not-allowed items-center gap-3 rounded-lg px-3 py-2 text-sm text-[#555]">
        <Icon size={16} />
        <span className="flex-1">{label}</span>
        <Lock size={12} />
      </div>
    );
  }
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
          isActive ? "bg-[rgba(255,255,255,0.1)] text-white" : "text-[#aaa] hover:bg-[rgba(255,255,255,0.06)] hover:text-white"
        )
      }
    >
      <Icon size={16} />
      <span>{label}</span>
    </NavLink>
  );
}

export function Sidebar() {
  const { me, switchOrg, logout } = useSession();
  const [orgMenuOpen, setOrgMenuOpen] = useState(false);
  const features = ((me?.active_org as unknown as { features?: Record<string, boolean> } | null)?.features) ?? {};

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-[#1a1a1a] bg-black">
      <div className="relative border-b border-[#1a1a1a] p-4">
        <button
          onClick={() => setOrgMenuOpen((v) => !v)}
          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-[rgba(255,255,255,0.06)]"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-purple-600 text-xs font-semibold text-white">
            {me?.active_org?.name?.[0] ?? "?"}
          </div>
          <span className="flex-1 truncate text-sm font-medium text-white">{me?.active_org?.name ?? "Select org"}</span>
          <ChevronDown size={14} className="text-[#666]" />
        </button>
        {orgMenuOpen && me && (
          <div className="absolute left-4 right-4 top-full z-10 mt-1 rounded-lg border border-[#2a2a2a] bg-[#0a0a0a] p-1 shadow-xl">
            {me.organizations.map((o) => (
              <button
                key={o.id}
                onClick={() => {
                  switchOrg(o.id);
                  setOrgMenuOpen(false);
                }}
                className={cn(
                  "block w-full truncate rounded-md px-2.5 py-1.5 text-left text-sm hover:bg-[rgba(255,255,255,0.08)]",
                  o.id === me.active_org?.id ? "text-white" : "text-[#aaa]"
                )}
              >
                {o.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <div className="space-y-0.5">
          {NAV.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </div>
        <div className="my-3 h-px bg-[#1a1a1a]" />
        <div className="space-y-0.5">
          {NAV2.map((item) => (
            <NavItem key={item.to} {...item} locked={item.feature ? !features[item.feature] : undefined} />
          ))}
        </div>
        <div className="my-3 h-px bg-[#1a1a1a]" />
        <div className="space-y-0.5">
          <NavItem to="/settings" label="Settings" icon={Settings} />
        </div>
      </nav>

      <div className="border-t border-[#1a1a1a] p-3">
        <button
          onClick={() => logout()}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-[rgba(255,255,255,0.06)]"
        >
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-700 text-xs font-semibold text-white">
            {me?.user.name?.[0] ?? "?"}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm text-white">{me?.user.name}</div>
            <div className="truncate text-xs text-[#666]">{me?.user.email}</div>
          </div>
        </button>
      </div>
    </aside>
  );
}
