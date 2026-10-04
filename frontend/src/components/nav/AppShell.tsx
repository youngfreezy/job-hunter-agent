// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { signIn } from "next-auth/react";
import {
  Bot,
  ChevronDown,
  ChevronsUpDown,
  Clock,
  Home,
  List,
  Menu,
  Plus,
  Wrench,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Wordmark } from "@/components/brand/Wordmark";
import { NotificationBanner } from "@/components/NotificationBanner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { API_BASE, apiFetch, getAuthHeaders } from "@/lib/api";

declare global {
  interface Window {
    umami?: {
      track: (event: string, data?: Record<string, unknown>) => void;
      identify: (data: Record<string, unknown>) => void;
    };
  }
}

type NavItem = { href: string; label: string; icon: typeof Home; match: string[] };

const PRIMARY: NavItem[] = [
  { href: "/dashboard", label: "Home", icon: Home, match: ["/dashboard", "/session", "/history"] },
  { href: "/apply", label: "Applications", icon: List, match: ["/apply"] },
  { href: "/autopilot", label: "Autopilot", icon: Clock, match: ["/autopilot"] },
];

const TOOLS = [
  { href: "/interview-prep", label: "Interview practice" },
  { href: "/career-pivot", label: "Career change" },
  { href: "/freelance", label: "Freelance practice" },
];

function matches(pathname: string, prefixes: string[]) {
  return prefixes.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

async function handleSignOut() {
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (key?.startsWith("jh_")) localStorage.removeItem(key);
  }
  sessionStorage.clear();
  const { signOut } = await import("next-auth/react");
  signOut({ callbackUrl: "/" });
}

type Account = { name: string | null; email: string | null; credits: number | null; free: number };

function useAccount() {
  const [account, setAccount] = useState<Account>({ name: null, email: null, credits: null, free: 0 });
  const [showGoogleBanner, setShowGoogleBanner] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const auth = await getAuthHeaders();
        const [walletRes, meRes] = await Promise.all([
          apiFetch(`${API_BASE}/api/billing/wallet`, { headers: auth }),
          apiFetch(`${API_BASE}/api/auth/me`, { headers: auth }),
        ]);
        if (walletRes.ok) {
          const w = await walletRes.json();
          setAccount((a) => ({ ...a, credits: w.balance ?? 0, free: w.free_remaining ?? 0 }));
        }
        if (meRes.ok) {
          const user = (await meRes.json()).user;
          setAccount((a) => ({ ...a, name: user?.name ?? null, email: user?.email ?? null }));
          if (user?.auth_provider === "email" && !sessionStorage.getItem("jh_google_banner_dismissed")) {
            setShowGoogleBanner(true);
          }
          if (user?.id && window.umami) {
            window.umami.identify({ userId: user.id, name: user.name || user.email, email: user.email });
          }
        }
      } catch {
        /* the shell still works without the account line */
      }
    })();
  }, []);

  return { account, showGoogleBanner, setShowGoogleBanner };
}

export function balanceLine(a: Account) {
  if (a.credits === null) return "";
  const credits = `${Math.floor(a.credits)} ${a.credits === 1 ? "credit" : "credits"}`;
  return a.free > 0 ? `${credits} · ${a.free} free` : credits;
}

function AccountMenu({ account, align = "start" }: { account: Account; align?: "start" | "end" }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex w-full items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-left text-sm transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium text-foreground">{account.name ?? "Account"}</span>
          <span className="block truncate font-mono text-xs text-muted-foreground">
            {balanceLine(account) || " "}
          </span>
        </span>
        <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} side="top" className="w-60">
        {account.email && (
          <DropdownMenuLabel className="truncate font-normal text-muted-foreground">
            {account.email}
          </DropdownMenuLabel>
        )}
        <DropdownMenuItem asChild>
          <Link href="/billing">Plan and credits</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings">Settings</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/account">Profile</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/developer">API and webhooks</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void handleSignOut()}>Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function NavLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const toolsActive = TOOLS.some((t) => matches(pathname, [t.href]));
  const [toolsOpen, setToolsOpen] = useState(toolsActive);
  useEffect(() => {
    if (toolsActive) setToolsOpen(true);
  }, [toolsActive]);

  const item = (active: boolean) =>
    cn(
      "flex min-h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm transition-colors [@media(pointer:coarse)]:min-h-11",
      active
        ? "bg-primary/10 font-medium text-primary"
        : "text-muted-foreground hover:bg-surface-2 hover:text-foreground"
    );

  return (
    <ul className="flex flex-col gap-0.5">
      {PRIMARY.map(({ href, label, icon: Icon, match }) => {
        const active = matches(pathname, match);
        return (
          <li key={href}>
            <Link href={href} aria-current={active ? "page" : undefined} className={item(active)} onClick={onNavigate}>
              <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
              {label}
            </Link>
          </li>
        );
      })}
      <li>
        <button
          type="button"
          aria-expanded={toolsOpen}
          aria-controls="nav-tools"
          onClick={() => setToolsOpen((o) => !o)}
          className={cn(item(false), "w-full", toolsActive && !toolsOpen && "text-foreground")}
        >
          <Wrench className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
          <span className="flex-1 text-left">Tools</span>
          <ChevronDown
            className={cn("h-4 w-4 transition-transform duration-150", toolsOpen && "rotate-180")}
            aria-hidden="true"
          />
        </button>
        <ul id="nav-tools" hidden={!toolsOpen} className="mt-0.5 flex flex-col gap-0.5 pl-[26px]">
          {TOOLS.map((t) => {
            const active = matches(pathname, [t.href]);
            return (
              <li key={t.href}>
                <Link
                  href={t.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(item(active), "min-h-8 text-[13px]")}
                  onClick={onNavigate}
                >
                  {t.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </li>
    </ul>
  );
}

function NewSearchButton({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link
      href="/session/new"
      onClick={onNavigate}
      className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-primary-hover/40 bg-primary px-3 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover [@media(pointer:coarse)]:h-11"
    >
      <Plus className="h-4 w-4" aria-hidden="true" />
      New search
    </Link>
  );
}

/**
 * The signed-in shell. A 232px rail from 1024px, a top bar with a menu sheet from 640px,
 * and a bottom tab bar on phones.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "";
  const { account, showGoogleBanner, setShowGoogleBanner } = useAccount();
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => setSheetOpen(false), [pathname]);
  useEffect(() => {
    if (!sheetOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSheetOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheetOpen]);

  return (
    <div className="min-h-screen bg-background lg:pl-[232px]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[100] focus:rounded-lg focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow"
      >
        Skip to content
      </a>

      {/* Rail, 1024px and up */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[232px] flex-col gap-5 border-r border-border bg-card px-3 py-4 lg:flex">
        <Wordmark href="/dashboard" className="px-2.5" />
        <NewSearchButton />
        <nav aria-label="Main" className="flex-1 overflow-y-auto">
          <NavLinks pathname={pathname} />
        </nav>
        <AccountMenu account={account} />
      </aside>

      {/* Top bar, under 1024px */}
      <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b border-border bg-card px-4 lg:hidden">
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          aria-label="Open menu"
          aria-expanded={sheetOpen}
          className="-ml-2 hidden h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-surface-2 sm:inline-flex"
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
        <Wordmark href="/dashboard" />
        <span className="ml-auto hidden truncate font-mono text-xs text-muted-foreground min-[400px]:block">
          {balanceLine(account)}
        </span>
        <Link
          href="/session/new"
          aria-label="New search"
          className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary-hover max-[399px]:ml-auto"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">New search</span>
        </Link>
      </header>

      {/* Menu sheet, 640 to 1023px */}
      {sheetOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button
            type="button"
            aria-label="Close menu"
            className="absolute inset-0 bg-foreground/30"
            onClick={() => setSheetOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex w-[280px] flex-col gap-5 border-r border-border bg-card px-3 py-4 shadow-xl">
            <div className="flex items-center justify-between">
              <Wordmark href="/dashboard" className="px-2.5" />
              <button
                type="button"
                onClick={() => setSheetOpen(false)}
                aria-label="Close menu"
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-surface-2"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            <NewSearchButton onNavigate={() => setSheetOpen(false)} />
            <nav aria-label="Main" className="flex-1 overflow-y-auto">
              <NavLinks pathname={pathname} onNavigate={() => setSheetOpen(false)} />
            </nav>
            <AccountMenu account={account} />
          </div>
        </div>
      )}

      {showGoogleBanner && (
        <NotificationBanner
          label="Connect Google"
          message="to enter verification codes from job sites automatically during applications."
          action={{ text: "Connect Google", onClick: () => signIn("google", { callbackUrl: window.location.href }) }}
          onDismiss={() => {
            setShowGoogleBanner(false);
            sessionStorage.setItem("jh_google_banner_dismissed", "1");
          }}
        />
      )}

      <main id="main" tabIndex={-1} className="focus:outline-none">
        {children}
      </main>

      {/* Bottom tab bar, under 640px */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-border bg-card pb-[env(safe-area-inset-bottom)] sm:hidden"
      >
        {[...PRIMARY, { href: "/interview-prep", label: "Tools", icon: Bot, match: TOOLS.map((t) => t.href) }].map(
          ({ href, label, icon: Icon, match }) => {
            const active = matches(pathname, match);
            return label === "Tools" ? (
              <DropdownMenu key={label}>
                <DropdownMenuTrigger
                  className={cn(
                    "flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium",
                    active ? "text-primary" : "text-muted-foreground"
                  )}
                >
                  <Wrench className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
                  Tools
                </DropdownMenuTrigger>
                <DropdownMenuContent side="top" align="end" className="w-56">
                  {TOOLS.map((t) => (
                    <DropdownMenuItem key={t.href} asChild>
                      <Link href={t.href}>{t.label}</Link>
                    </DropdownMenuItem>
                  ))}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link href="/settings">Settings</Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <Link href="/billing">Plan and credits</Link>
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => void handleSignOut()}>Sign out</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium",
                  active ? "text-primary" : "text-muted-foreground"
                )}
              >
                <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
                {label}
              </Link>
            );
          }
        )}
      </nav>
    </div>
  );
}
