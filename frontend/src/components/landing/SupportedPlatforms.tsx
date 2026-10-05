// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Card, CardContent } from "@/components/ui/card";
import { indeedEasyApplyOnly } from "@/lib/indeed-policy";


export function SupportedPlatforms() {
  return (<>
    {/* Supported Platforms */}
    <section className="px-6 pb-16">
      <div className="mx-auto max-w-6xl">
        <Card className="rounded-[28px] border-zinc-200/80 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <CardContent className="py-8">
            <h3 className="mb-6 text-center text-lg font-semibold">
              {indeedEasyApplyOnly ? "Indeed Easy Apply, powered by a real browser" : "Works with all major job boards and ATS platforms"}
            </h3>
            <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm font-medium text-zinc-600 dark:text-zinc-400">
              {(indeedEasyApplyOnly ? ["Indeed Easy Apply", "Browserbase", "Stagehand"] : [
                "LinkedIn",
                "Indeed",
                "Glassdoor",
                "ZipRecruiter",
                "Greenhouse",
                "Lever",
                "Workday",
                "Ashby",
                "iCIMS",
              ]).map((platform) => (
                <span
                  key={platform}
                  className="rounded-lg border border-zinc-200 px-3 py-1.5 dark:border-zinc-700"
                >
                  {platform}
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </section>

  </>);
}
