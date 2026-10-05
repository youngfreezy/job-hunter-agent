// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

import { platformHighlights } from "./content";

export function PlatformHighlights() {
  return (<>
    {/* Platform Highlights */}
    <section className="px-6 pb-16">
      <div className="mx-auto max-w-6xl">
        <h2 className="mb-8 text-center text-2xl font-bold">
          Why job seekers choose JobHunter Agent
        </h2>
        <div className="grid gap-6 md:grid-cols-3">
          {platformHighlights.map((h) => (
            <Card
              key={h.title}
              className="rounded-3xl border-zinc-200/80 bg-white/90 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
            >
              <CardContent className="p-6">
                <Badge
                  variant="secondary"
                  className="mb-3 bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                >
                  {h.stat}
                </Badge>
                <p className="text-sm font-semibold text-zinc-900 dark:text-white">{h.title}</p>
                <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                  {h.desc}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>

  </>);
}
