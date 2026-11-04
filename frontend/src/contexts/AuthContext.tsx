import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, refreshAccessToken, setAuthLostHandler, tokens } from "@/lib/api";
import { useConnection } from "@/contexts/ConnectionContext";
import type { AuthResponse, User } from "@/types/api";

type AuthStatus = "unknown" | "authenticated" | "anonymous";

interface AuthValue {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; password: string; full_name?: string; invite_code?: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { state, reconnectCount } = useConnection();
  const qc = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>("unknown");
  const [user, setUser] = useState<User | null>(null);
  const restoring = useRef(false);

  const clear = useCallback(() => {
    tokens.set(null);
    setUser(null);
    setStatus("anonymous");
    qc.clear();
  }, [qc]);

  useEffect(() => {
    setAuthLostHandler(clear);
  }, [clear]);

  // Restore the session whenever the backend is (or becomes) reachable.
  const restore = useCallback(async () => {
    if (restoring.current) return;
    restoring.current = true;
    try {
      if (!tokens.access) {
        if (!tokens.refresh) {
          setStatus("anonymous");
          return;
        }
        const access = await refreshAccessToken();
        if (!access) {
          if (!tokens.refresh) setStatus("anonymous"); // rejected; otherwise a network blip, keep waiting
          return;
        }
      }
      const me = await api.get<User>("/auth/me");
      setUser(me.data);
      setStatus("authenticated");
    } catch {
      if (!tokens.refresh) setStatus("anonymous");
    } finally {
      restoring.current = false;
    }
  }, []);

  useEffect(() => {
    if (state === "online") void restore();
  }, [state, restore]);

  // After a reconnect, reload all data the UI shows.
  useEffect(() => {
    if (reconnectCount > 0) void qc.invalidateQueries();
  }, [reconnectCount, qc]);

  const accept = useCallback((data: AuthResponse) => {
    tokens.set(data);
    setUser(data.user);
    setStatus("authenticated");
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<AuthResponse>("/auth/login", { email, password });
    accept(res.data);
  }, [accept]);

  const register = useCallback(async (data: { email: string; password: string; full_name?: string; invite_code?: string }) => {
    const res = await api.post<AuthResponse>("/auth/register", data);
    accept(res.data);
  }, [accept]);

  const logout = useCallback(async () => {
    const rt = tokens.refresh;
    try {
      if (rt && tokens.access) await api.post("/auth/logout", { refresh_token: rt });
    } catch {
      /* best effort: the local session is cleared regardless */
    }
    clear();
  }, [clear]);

  const refreshUser = useCallback(async () => {
    const me = await api.get<User>("/auth/me");
    setUser(me.data);
  }, []);

  const value = useMemo(() => ({ status, user, login, register, logout, refreshUser }), [status, user, login, register, logout, refreshUser]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
