import { Navigate, Outlet } from "react-router-dom";
import { useSession } from "../store/session";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const { me, loaded, loading } = useSession();

  if (!loaded || loading) {
    return <div className="flex h-screen items-center justify-center text-sm text-[#666]">Loading…</div>;
  }
  if (!me) {
    return <Navigate to="/login" replace />;
  }
  if (!me.active_org) {
    return <Navigate to="/onboarding" replace />;
  }

  return (
    <div className="flex h-screen bg-black">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <main className="page-in flex-1 overflow-y-auto p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
