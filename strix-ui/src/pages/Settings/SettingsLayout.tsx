import { NavLink, Outlet } from "react-router-dom";
import { cn } from "../../lib/cn";

const TABS = [
  { to: "/settings", label: "General", end: true },
  { to: "/settings/llm-provider", label: "LLM Provider" },
  { to: "/settings/api-access", label: "API Access" },
  { to: "/settings/audit-logs", label: "Logs & Audit" },
  { to: "/settings/members", label: "Members" },
  { to: "/settings/billing", label: "Billing" },
  { to: "/settings/help-support", label: "Help & Support" },
];

export function SettingsLayout() {
  return (
    <div className="flex gap-10">
      <nav className="w-44 shrink-0 space-y-0.5">
        <div className="mb-3 px-3 text-xs font-medium uppercase tracking-wide text-[#666]">Settings</div>
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              cn(
                "block rounded-lg px-3 py-2 text-sm",
                isActive ? "bg-[rgba(255,255,255,0.1)] text-white" : "text-[#aaa] hover:bg-[rgba(255,255,255,0.06)] hover:text-white"
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <div className="max-w-2xl flex-1">
        <Outlet />
      </div>
    </div>
  );
}
