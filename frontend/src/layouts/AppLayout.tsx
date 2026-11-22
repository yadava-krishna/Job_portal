import { Suspense, useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { LogOut, Menu, PanelLeftClose, PanelLeftOpen, Search, X } from "lucide-react";
import { NotificationBell } from "@/components/app/discovery";
import { CommandMenu, useCommandMenuShortcut } from "@/components/app/CommandMenu";
import { Skeleton } from "@/components/ui/skeleton";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/contexts/AuthContext";
import { useConnection } from "@/contexts/ConnectionContext";
import { useHeartbeat } from "@/hooks/useHeartbeat";
import { useOverview } from "@/features/dashboard/queries";
import { cn } from "@/lib/utils";
import { timeAgo } from "@/lib/format";
import { areaFor, areas, footerItems, type NavArea } from "@/layouts/navigation";

const COLLAPSE_KEY = "jobpilot.sidebar";
const WIDE = 240;
const NARROW = 72;

function readCollapsed(): boolean {
  try { return localStorage.getItem(COLLAPSE_KEY) === "collapsed"; } catch { return false; }
}

function LiveIndicator() {
  const c = useConnection();
  const online = c.state === "online";
  const checked = online && c.lastOnlineAt ? `checked ${timeAgo(new Date(c.lastOnlineAt).toISOString())}` : "";
  return (
    <div className="flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs" title={`${c.baseUrl ?? ""} ${checked}`}>
      <span className="relative flex size-2">
        {online && <span className="absolute inset-0 animate-ping rounded-full bg-success/50 [animation-duration:2.4s]" />}
        <span className={cn("relative size-2 rounded-full", online ? "bg-success" : "bg-destructive")} />
      </span>
      <span className="font-medium">{online ? "Live" : "Offline"}</span>
    </div>
  );
}

function isActive(pathname: string, to: string) {
  return pathname === to || pathname.startsWith(to + "/");
}

/** A label that becomes a tooltip when the sidebar is collapsed. */
function Tip({ show, label, children }: { show: boolean; label: string; children: React.ReactElement }) {
  if (!show) return children;
  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent side="right" sideOffset={10}>{label}</TooltipContent>
    </Tooltip>
  );
}

function Count({ n, collapsed, tone = "route" }: { n?: number; collapsed: boolean; tone?: "route" | "coral" }) {
  if (!n) return null;
  if (collapsed) return <span className={cn("absolute top-1.5 right-2 size-2 rounded-full ring-2 ring-sidebar", tone === "coral" ? "bg-coral" : "bg-route")} aria-hidden />;
  return (
    <span className={cn("readout ml-auto rounded-full px-1.5 py-px text-[11px] font-medium", tone === "coral" ? "bg-peach text-coral-ink" : "bg-route-tint text-route")}>
      {n > 99 ? "99+" : n}
    </span>
  );
}

function SideNav({ collapsed, onToggle, onNavigate, onSearch, mobile }: {
  collapsed: boolean; onToggle?: () => void; onNavigate?: () => void; onSearch: () => void; mobile?: boolean;
}) {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const overview = useOverview();
  const current = areaFor(pathname);
  const name = user?.full_name || user?.email || "";
  const initials = name.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("");
  const counts: Record<string, { n?: number; tone?: "route" | "coral"; label?: string }> = {
    jobs: { n: overview.data?.new_jobs.count, label: "new matches" },
    applications: { n: overview.data?.attention.length, tone: "coral", label: "need you" },
  };

  // One highlight that slides to the active destination instead of jumping.
  const navRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Record<string, HTMLAnchorElement | null>>({});
  const [pill, setPill] = useState<{ y: number; h: number } | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const el = current ? itemRefs.current[current.key] : null;
      const box = navRef.current;
      if (!el || !box) { setPill(null); return; }
      setPill({ y: el.offsetTop, h: el.offsetHeight });
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (navRef.current) ro.observe(navRef.current);
    return () => ro.disconnect();
  }, [current, collapsed]);

  const signOut = async () => { await logout(); navigate("/login"); };
  const groups: { label: string; items: NavArea[] }[] = [
    { label: "Workspace", items: areas.filter((a) => a.key !== "career") },
    { label: "Grow", items: areas.filter((a) => a.key === "career") },
  ];

  return (
    <div className="flex h-full flex-col">
      <div className={cn("flex items-center", collapsed ? "flex-col gap-3" : "justify-between pr-1 pl-1.5")}>
        <Brand compact={collapsed} />
        {onToggle && (
          <Tip show={collapsed} label="Expand sidebar  [">
            <Button variant="ghost" size="icon-sm" onClick={onToggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}
                    className="text-muted-foreground" data-testid="sidebar-toggle">
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            </Button>
          </Tip>
        )}
      </div>

      <Tip show={collapsed} label="Search or jump to  ⌘K">
        <button type="button" onClick={onSearch} data-testid="open-command-menu" aria-label="Search or jump to"
                className={cn("mt-5 flex items-center gap-2 rounded-xl border bg-background text-sm text-muted-foreground transition-colors duration-150 hover:border-foreground/20 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
                  collapsed ? "mx-auto size-10 justify-center" : "w-full px-3 py-2 text-left")}>
          <Search className="size-4 shrink-0" aria-hidden />
          {!collapsed && <><span className="flex-1 truncate">Search or jump to…</span><kbd className="readout rounded-md border bg-card px-1.5 text-[10px]">⌘K</kbd></>}
        </button>
      </Tip>

      <nav aria-label="Main" className="relative mt-5" ref={navRef}>
        {pill && (
          <span aria-hidden className="pointer-events-none absolute inset-x-0 top-0 rounded-xl bg-sidebar-accent transition-[transform,height] duration-[260ms] ease-[cubic-bezier(.2,0,0,1)]"
                style={{ transform: `translateY(${pill.y}px)`, height: pill.h }}>
            <span className="absolute top-2 bottom-2 left-0 w-[3px] rounded-r-full bg-route" />
          </span>
        )}
        {groups.map((g, gi) => (
          <div key={g.label} className={cn(gi > 0 && "mt-4")}>
            {collapsed ? (gi > 0 && <div className="mx-auto mb-3 h-px w-6 bg-border" aria-hidden />)
              : <div className="eyebrow mb-1.5 px-3 text-[10px]">{g.label}</div>}
            {g.items.map((a) => {
              const open = current?.key === a.key;
              const Icon = a.icon;
              const c = counts[a.key];
              return (
                <div key={a.key}>
                  <Tip show={collapsed} label={c?.n ? `${a.label} · ${c.n} ${c.label}` : a.label}>
                    <NavLink to={a.to} onClick={onNavigate} end={a.children.length === 0} ref={(el) => { itemRefs.current[a.key] = el; }}
                             aria-current={open ? "page" : undefined} aria-label={collapsed ? a.label : undefined}
                             className={cn("group relative flex h-10 items-center gap-3 rounded-xl text-[14px] font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-ring",
                               collapsed ? "mx-auto w-11 justify-center" : "px-3",
                               open ? "text-heading" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground")}>
                      <Icon className={cn("relative size-[18px] shrink-0 transition-colors duration-150", open ? "text-route" : "")} aria-hidden />
                      {!collapsed && <span className="relative truncate">{a.label}</span>}
                      <Count n={c?.n} collapsed={collapsed} tone={c?.tone} />
                    </NavLink>
                  </Tip>
                  {/* Every section's pages are listed whenever the sidebar is expanded (not only the open section's). */}
                  {!collapsed && a.children.length > 1 && (
                    <div className="relative mt-1 mb-2 ml-[22px] border-l border-border pl-3" data-testid={`nav-children-${a.key}`}>
                      {a.children.map((ch) => {
                        const on = isActive(pathname, ch.to);
                        return (
                          <NavLink key={ch.to} to={ch.to} onClick={onNavigate}
                                   className={cn("relative flex items-center rounded-lg px-2.5 py-1.5 text-[13px] transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-ring",
                                     on ? "font-semibold text-heading" : "text-muted-foreground hover:text-foreground")}>
                            {on && <span className="absolute top-1/2 -left-[15.5px] h-4 w-[3px] -translate-y-1/2 rounded-full bg-violet" aria-hidden />}
                            {ch.label}
                          </NavLink>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="mt-auto flex flex-col gap-1 pt-6">
        {footerItems(user?.role).map(({ to, label, icon: Icon }) => (
          <Tip key={to} show={collapsed} label={label}>
            <NavLink to={to} onClick={onNavigate} aria-label={collapsed ? label : undefined}
                     className={({ isActive: on }) => cn("flex h-9 items-center gap-3 rounded-xl text-[13px] font-medium transition-colors duration-150 focus-visible:outline-2 focus-visible:outline-ring",
                       collapsed ? "mx-auto w-11 justify-center" : "px-3",
                       on ? "bg-sidebar-accent text-heading" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground")}>
              <Icon className="size-4 shrink-0" aria-hidden /> {!collapsed && label}
            </NavLink>
          </Tip>
        ))}
        <DropdownMenu>
          <DropdownMenuTrigger render={
            <button type="button" aria-label="Account menu"
                    className={cn("mt-2 flex items-center gap-3 rounded-2xl text-left transition-colors duration-150 hover:bg-muted/70 focus-visible:outline-2 focus-visible:outline-ring",
                      collapsed ? "mx-auto p-1" : "w-full border bg-background p-2")} />}>
            <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-route to-route-bright font-display text-[13px] font-bold text-white" aria-hidden>{initials || "·"}</span>
            {!collapsed && (
              <span className="min-w-0 flex-1 leading-tight">
                <span className="block truncate text-[13px] font-semibold">{user?.full_name || "Your account"}</span>
                <span className="block truncate text-[11px] text-muted-foreground">{user?.email}</span>
              </span>
            )}
          </DropdownMenuTrigger>
          <DropdownMenuContent side={mobile ? "top" : "right"} align="end" className="min-w-56">
            <DropdownMenuLabel className="truncate">{user?.email}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => { onNavigate?.(); navigate("/settings?tab=account"); }}>Account & privacy</DropdownMenuItem>
            <DropdownMenuItem onClick={signOut}><LogOut /> Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}

export function AppLayout() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [cmd, setCmd] = useState(false);
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = useCallback(() => setCollapsed((c) => {
    try { localStorage.setItem(COLLAPSE_KEY, c ? "expanded" : "collapsed"); } catch { /* preference only */ }
    return !c;
  }), []);
  const openCmd = useCallback(() => { setOpen(false); setCmd(true); }, []);
  useCommandMenuShortcut(openCmd);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && open) setOpen(false);
      const t = e.target as HTMLElement;
      if (e.key === "[" && !e.metaKey && !e.ctrlKey && !e.altKey && !t.closest("input, textarea, select, [contenteditable=true]")) toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, toggle]);

  useHeartbeat(true);
  const area = areaFor(pathname);
  const leaf = area?.children.find((c) => isActive(pathname, c.to));
  const width = collapsed ? NARROW : WIDE;

  return (
    <div className="min-h-dvh bg-background" style={{ ["--sb" as string]: `${width}px` }}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:shadow-md focus:outline-2 focus:outline-ring">Skip to main content</a>
      <aside aria-label="Sidebar" data-collapsed={collapsed || undefined}
             className="fixed inset-y-0 left-0 z-30 hidden w-(--sb) flex-col overflow-hidden border-r border-sidebar-border bg-sidebar px-3 py-4 transition-[width] duration-[260ms] ease-[cubic-bezier(.2,0,0,1)] lg:flex">
        <SideNav collapsed={collapsed} onToggle={toggle} onSearch={openCmd} />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-[#171927]/40 backdrop-blur-[2px] animate-in fade-in-0 duration-200" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-[280px] flex-col bg-sidebar px-3 py-4 shadow-[var(--shadow-overlay)] animate-in slide-in-from-left-8 fade-in-0 duration-[260ms]">
            <Button size="icon-sm" variant="ghost" className="absolute top-4 right-3" onClick={() => setOpen(false)} aria-label="Close menu"><X /></Button>
            <SideNav collapsed={false} onNavigate={() => setOpen(false)} onSearch={openCmd} mobile />
          </aside>
        </div>
      )}

      <div className="transition-[padding] duration-[260ms] ease-[cubic-bezier(.2,0,0,1)] lg:pl-(--sb)">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b border-transparent bg-background/85 px-4 backdrop-blur-md sm:px-8">
          <div className="flex min-w-0 items-center gap-2">
            <Button size="icon-sm" variant="ghost" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu /></Button>
            <div className="lg:hidden"><Brand compact /></div>
            {area && (
              <nav aria-label="Breadcrumb" className="hidden items-center gap-2 text-[13px] text-muted-foreground lg:flex">
                <span>{area.label}</span>
                {leaf && area.children.length > 1 && <><span aria-hidden>/</span><span className="font-medium text-foreground">{leaf.label}</span></>}
              </nav>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={openCmd} aria-label="Search or jump to"><Search /></Button>
            <ThemeToggle />
            <NotificationBell />
            <LiveIndicator />
          </div>
        </header>
        {area && area.children.length > 1 && (
          <div className="flex gap-1 overflow-x-auto px-4 pb-2 sm:px-8 lg:hidden">
            {area.children.map((c) => (
              <NavLink key={c.to} to={c.to}
                       className={cn("shrink-0 rounded-full border px-3 py-1 text-[13px]", isActive(pathname, c.to) ? "border-route bg-route-tint font-semibold text-route" : "bg-card text-muted-foreground")}>
                {c.label}
              </NavLink>
            ))}
          </div>
        )}
        <main id="main" tabIndex={-1} className="mx-auto max-w-[1320px] px-4 pt-3 pb-14 outline-none sm:px-8">
          <Suspense fallback={<PageSkeleton />}>
            <div key={pathname} className="jp-rise"><Outlet /></div>
          </Suspense>
        </main>
      </div>
      <CommandMenu open={cmd} onOpenChange={setCmd} role={user?.role} />
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div role="status" aria-label="Loading page" className="space-y-5 py-3">
      <Skeleton className="h-8 w-64 rounded-lg" />
      <Skeleton className="h-4 w-96 max-w-full" />
      <div className="grid gap-4 md:grid-cols-3"><Skeleton className="h-32 rounded-2xl" /><Skeleton className="h-32 rounded-2xl" /><Skeleton className="h-32 rounded-2xl" /></div>
      <Skeleton className="h-56 rounded-2xl" />
    </div>
  );
}

/** The mark: a cobalt-to-violet tile with a dotted flight path, the wordmark in Manrope. */
export function BrandMark({ className }: { className?: string }) {
  // Each mark gets its own gradient id: a shared id would point at the copy inside the hidden desktop sidebar on phones.
  const gid = `jp-mark-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn("size-8 shrink-0", className)}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#365CF5" /><stop offset="1" stopColor="#7754E8" /></linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gid})`} />
      <path d="M7.5 22 L13 16.5 L17.5 19 L24.5 10.5" fill="none" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="0.1 4.1" />
      <circle cx="24.5" cy="10.5" r="2.5" fill="#FF6B76" />
      <circle cx="7.5" cy="22" r="1.6" fill="white" opacity="0.85" />
    </svg>
  );
}

export function Brand({ compact = false }: { compact?: boolean }): ReactNode {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark className="size-8" />
      {!compact && <span className="font-display text-[19px] font-extrabold tracking-[-0.03em] text-heading">JobPilot</span>}
    </div>
  );
}
