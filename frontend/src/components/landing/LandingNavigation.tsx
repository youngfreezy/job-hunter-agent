// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Button } from "@/components/ui/button";
import Link from "next/link";


export function LandingNavigation() {
  return (<>
    {/* Nav */}
    <nav className="border-b border-zinc-200/80 bg-white/80 px-6 py-4 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/80 sticky top-0 z-50">
      <div className="mx-auto flex max-w-7xl items-center justify-between">
        <span className="text-xl font-bold tracking-tight">JobHunter Agent</span>
        <div className="flex items-center gap-4">
          <a
            href="#how-it-works"
            className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
          >
            How It Works
          </a>
          <a
            href="#pricing"
            className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
          >
            Pricing
          </a>
          <a
            href="#faq"
            className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
          >
            FAQ
          </a>
          <a
            href="#about"
            className="hidden sm:inline text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
          >
            About
          </a>
          <Link href="/try">
            <Button size="sm" data-umami-event="cta-try-free" data-umami-event-location="nav">
              Try Free
            </Button>
          </Link>
        </div>
      </div>
    </nav>

  </>);
}
