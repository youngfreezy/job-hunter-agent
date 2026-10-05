// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import Link from "next/link";


export function FinalCallToAction() {
  return (<>
    {/* Final CTA */}
    <section className="px-6 py-20">
      <div className="mx-auto max-w-4xl">
        <Card className="rounded-[28px] border-emerald-200 bg-card dark:border-emerald-900">
          <CardContent className="py-10 text-center">
            <h3 className="text-2xl font-bold">Ready to automate your job search?</h3>
            <p className="mx-auto mt-3 max-w-xl text-sm text-zinc-600 dark:text-zinc-400">
              Sign in with Google, upload your resume, and review your search before
              the agent starts applying.
            </p>
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <Link href="/try">
                <Button
                  size="lg"
                  data-umami-event="cta-try-free"
                  data-umami-event-location="bottom"
                >
                  Try Free with Google
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>

  </>);
}
