// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// Signed-in app routes have their own shell and no marketing footer.
const APP_PREFIXES = [
  "/dashboard", "/session", "/apply", "/autopilot", "/billing", "/career-pivot", "/developer",
  "/freelance", "/history", "/interview-prep", "/marketplace", "/quick-apply", "/settings", "/account",
];

export function Footer() {
  const pathname = usePathname() ?? "";
  if (APP_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + "/"))) return null;
  return (
    <footer className="border-t border-zinc-200 px-6 py-10 dark:border-zinc-800">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-col items-center justify-between gap-6 md:flex-row">
          <div>
            <p className="text-sm font-semibold text-zinc-900 dark:text-white">
              JobHunter Agent
            </p>
            <p className="text-xs text-zinc-500">
              &copy; {new Date().getFullYear()} V2 Software LLC. All rights
              reserved.
            </p>
          </div>
          <div className="flex gap-6 text-sm text-zinc-500">
            <Link
              href="/about"
              className="hover:text-zinc-900 dark:hover:text-white"
            >
              About
            </Link>
            <Link
              href="/terms"
              className="hover:text-zinc-900 dark:hover:text-white"
            >
              Terms of Service
            </Link>
            <Link
              href="/privacy"
              className="hover:text-zinc-900 dark:hover:text-white"
            >
              Privacy Policy
            </Link>
            <a
              href="mailto:support@jobhunteragent.com"
              className="hover:text-zinc-900 dark:hover:text-white"
            >
              Contact
            </a>
            <Link
              href="/status"
              className="hover:text-zinc-900 dark:hover:text-white"
            >
              Status
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
