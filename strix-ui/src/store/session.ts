import { create } from "zustand";
import { api, setUnauthorizedHandler } from "../api/client";
import type { MeOut } from "../api/types";

interface SessionState {
  me: MeOut | null;
  loading: boolean;
  loaded: boolean;
  refresh: () => Promise<void>;
  switchOrg: (orgId: string) => Promise<void>;
  logout: () => Promise<void>;
  setMe: (me: MeOut) => void;
}

let sessionBoundaryHandler: (() => void) | null = null;

/** Called after logout, org switch, or 401 so React Query cannot keep
 * another org's (or a logged-out user's) cached lists on screen. */
export function setSessionBoundaryHandler(handler: (() => void) | null) {
  sessionBoundaryHandler = handler;
}

function crossedSessionBoundary() {
  sessionBoundaryHandler?.();
}

export const useSession = create<SessionState>((set) => ({
  me: null,
  loading: false,
  loaded: false,
  setMe: (me) => set({ me, loaded: true }),
  refresh: async () => {
    set({ loading: true });
    try {
      const me = await api.get<MeOut>("/api/auth/me");
      set({ me, loading: false, loaded: true });
    } catch {
      set({ me: null, loading: false, loaded: true });
    }
  },
  switchOrg: async (orgId: string) => {
    const me = await api.post<MeOut>("/api/auth/switch-org", { org_id: orgId });
    crossedSessionBoundary();
    set({ me });
  },
  logout: async () => {
    await api.post("/api/auth/logout");
    crossedSessionBoundary();
    set({ me: null, loaded: true, loading: false });
  },
}));

setUnauthorizedHandler(() => {
  crossedSessionBoundary();
  useSession.setState({ me: null, loaded: true, loading: false });
});
