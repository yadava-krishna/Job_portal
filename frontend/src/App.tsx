import { lazy, Suspense, useEffect } from "react";
import { HashRouter, Navigate, Outlet, Route, Routes, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { OfflineScreen } from "@/components/app/OfflineScreen";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { ConnectionProvider, useConnection } from "@/contexts/ConnectionContext";
import { AppLayout } from "@/layouts/AppLayout";
import { decodeClip, stashClip } from "@/lib/clipper";
import { LoginPage, RegisterPage } from "@/pages/AuthPages";
import { useOnboarding } from "@/services/queries";

// Pages are split into separate chunks (charts load only where they are used).
const AppliedPage = lazy(() => import("@/pages/AppliedPage").then((m) => ({ default: m.AppliedPage })));
const DashboardPage = lazy(() => import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage })));
const DiscoverPage = lazy(() => import("@/pages/DiscoverPage").then((m) => ({ default: m.DiscoverPage })));
const SavedPage = lazy(() => import("@/pages/DiscoverPage").then((m) => ({ default: m.SavedPage })));
const OnboardingPage = lazy(() => import("@/pages/OnboardingPage").then((m) => ({ default: m.OnboardingPage })));
const ReportsPage = lazy(() => import("@/pages/ReportsPage").then((m) => ({ default: m.ReportsPage })));
const SettingsPage = lazy(() => import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (count, err: unknown) => {
        const status = (err as { response?: { status?: number } })?.response?.status;
        return status === undefined ? count < 2 : status >= 500 && count < 2;
      },
      refetchOnWindowFocus: true,
    },
  },
});

function Splash({ text }: { text: string }) {
  return <div className="flex min-h-dvh items-center justify-center gap-2 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> {text}</div>;
}

/** Blocks the whole UI (search, apply, profile changes, downloads) unless the backend is online. */
function BackendGate() {
  const { state } = useConnection();
  if (state === "resolving" || state === "checking") return <Splash text="Connecting to the job portal…" />;
  if (state !== "online") return <OfflineScreen />;
  return <Suspense fallback={<Splash text="Loading…" />}><Outlet /></Suspense>;
}

function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "unknown") return <Splash text="Restoring your session…" />;
  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

function RequireOnboarded() {
  const { data, isLoading } = useOnboarding();
  if (isLoading) return <Splash text="Loading…" />;
  if (data && !data.completed) return <Navigate to="/onboarding" replace />;
  return <Outlet />;
}

function GuestOnly() {
  const { status } = useAuth();
  if (status === "unknown") return <Splash text="Restoring your session…" />;
  if (status === "authenticated") return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}

/** Landing point for the browser clipper: stash the captured job, then review it in Discover. */
function ClipRoute() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { status } = useAuth();
  useEffect(() => {
    const job = decodeClip(params.get("d"));
    if (job) stashClip(job);
    if (status === "authenticated") navigate("/discover", { replace: true });
    else if (status === "anonymous") navigate("/login", { replace: true, state: { from: "/discover" } });
  }, [params, status, navigate]);
  return <Splash text="Opening captured job…" />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConnectionProvider>
        <AuthProvider>
          <TooltipProvider>
            <HashRouter>
              <Routes>
                <Route element={<BackendGate />}>
                  <Route path="/clip" element={<ClipRoute />} />
                  <Route element={<GuestOnly />}>
                    <Route path="/login" element={<LoginPage />} />
                    <Route path="/register" element={<RegisterPage />} />
                  </Route>
                  <Route element={<RequireAuth />}>
                    <Route path="/onboarding" element={<OnboardingPage />} />
                    <Route element={<RequireOnboarded />}>
                      <Route element={<AppLayout />}>
                        <Route path="/dashboard" element={<DashboardPage />} />
                        <Route path="/discover" element={<DiscoverPage />} />
                        <Route path="/saved" element={<SavedPage />} />
                        <Route path="/applied" element={<AppliedPage />} />
                        <Route path="/reports" element={<ReportsPage />} />
                        <Route path="/settings" element={<SettingsPage />} />
                      </Route>
                    </Route>
                  </Route>
                  <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Route>
              </Routes>
            </HashRouter>
            <Toaster richColors position="top-right" />
          </TooltipProvider>
        </AuthProvider>
      </ConnectionProvider>
    </QueryClientProvider>
  );
}
