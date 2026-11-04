import { Suspense, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BarChart3, Loader2, Bookmark, Briefcase, FileSpreadsheet, LayoutDashboard, LogOut, Menu, Search, Settings, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import { useConnection } from "@/contexts/ConnectionContext";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/format";

const nav = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/discover", label: "Discover jobs", icon: Search },
  { to: "/saved", label: "Saved", icon: Bookmark },
  { to: "/applied", label: "Applications", icon: Briefcase },
  { to: "/reports", label: "Reports", icon: FileSpreadsheet },
  { to: "/settings", label: "Settings", icon: Settings },
];

function BackendIndicator() {
  const c = useConnection();
  const online = c.state === "online";
  return (
    <div className="flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs" title={c.baseUrl ?? ""}>
      <span className={cn("size-2 rounded-full", online ? "bg-emerald-500" : "bg-destructive animate-pulse")} />
      <span className="font-medium">{online ? "Backend online" : "Backend offline"}</span>
      {online && c.lastOnlineAt && <span className="hidden text-muted-foreground md:inline">· checked {timeAgo(new Date(c.lastOnlineAt).toISOString())}</span>}
    </div>
  );
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const links = (
    <nav className="flex flex-col gap-1">
      {nav.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} onClick={() => setOpen(false)}
                 className={({ isActive }) => cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                   isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
          <Icon className="size-4" /> {label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-dvh bg-muted/30">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r bg-background p-4 lg:flex">
        <Brand />
        <div className="mt-6 flex-1">{links}</div>
        <UserBox email={user?.email} onLogout={async () => { await logout(); navigate("/login"); }} />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-background p-4 shadow-xl">
            <div className="flex items-center justify-between"><Brand /><Button size="icon-sm" variant="ghost" onClick={() => setOpen(false)} aria-label="Close menu"><X /></Button></div>
            <div className="mt-6 flex-1">{links}</div>
            <UserBox email={user?.email} onLogout={async () => { await logout(); navigate("/login"); }} />
          </aside>
        </div>
      )}

      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b bg-background/90 px-4 backdrop-blur sm:px-6">
          <div className="flex items-center gap-2">
            <Button size="icon-sm" variant="ghost" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu /></Button>
            <div className="lg:hidden"><Brand compact /></div>
          </div>
          <BackendIndicator />
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
          {/* Keeps the navigation visible while a page chunk loads. */}
          <Suspense fallback={<div className="flex justify-center py-20 text-muted-foreground"><Loader2 className="animate-spin" /></div>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground"><BarChart3 className="size-4" /></div>
      {!compact && <div className="leading-tight"><div className="font-semibold">JobPilot</div><div className="text-xs text-muted-foreground">Job application portal</div></div>}
      {compact && <span className="font-semibold">JobPilot</span>}
    </div>
  );
}

function UserBox({ email, onLogout }: { email?: string; onLogout: () => void }) {
  return (
    <div className="border-t pt-3">
      <div className="truncate px-1 text-sm" title={email}>{email}</div>
      <Button variant="ghost" size="sm" className="mt-1 w-full justify-start" onClick={onLogout}><LogOut /> Sign out</Button>
    </div>
  );
}
