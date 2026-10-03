"use client";

import { Cloud, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

/** Temporary interview demo UI; disable NEXT_PUBLIC_BROWSERBASE_DEMO after the demo. */
export function BrowserbaseExplainer({ compact = false }: { compact?: boolean }) {
  if (process.env.NEXT_PUBLIC_BROWSERBASE_DEMO !== "true") return null;

  return (
    <Dialog>
      <div className={compact ? "" : "mb-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-muted/30 p-4"}>
        {!compact && (
          <div className="flex items-start gap-3">
            <Cloud className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold">A real browser, powered by <a href="https://www.browserbase.com/" target="_blank" rel="noopener noreferrer" className="underline underline-offset-4 focus-visible:outline focus-visible:outline-2">Browserbase<span className="sr-only"> (opens in a new tab)</span></a></p>
              <p className="mt-1 text-sm text-muted-foreground">Watch the agent search Indeed and work through applications.</p>
            </div>
          </div>
        )}
        <DialogTrigger asChild>
          <Button variant={compact ? "ghost" : "outline"} size="sm">How Browserbase works</Button>
        </DialogTrigger>
      </div>
      <DialogContent className="max-h-[90dvh] max-w-xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>How Browserbase powers this demo</DialogTitle>
          <DialogDescription>JobHunter plans the job search. Browserbase runs the browser that carries it out.</DialogDescription>
        </DialogHeader>
        <dl className="divide-y divide-border text-sm">
          {[
            ["Cloud browser", "Indeed opens in a Browserbase session. JobHunter searches and reads listings in that browser. Stagehand, Browserbase’s AI SDK, reads application pages and acts on natural-language instructions."],
            ["One Indeed login across sessions", "A saved Context preserves your Indeed login for discovery and subsequent applications. It belongs to your account; other JobHunter users do not share it."],
            ["Live View", "The browser embedded in this app shows the actual cloud session, so you can watch what the agent is doing."],
            ["CAPTCHA handling", "Browserbase’s managed solver is enabled for supported challenges. Some challenges, sign-in checks, or application questions may still need your input."],
            ["Stagehand application flow", "JobHunter interprets your prompt and ranks matches. Stagehand works through each Indeed form using your resume and saved answers. JobHunter checks the actual confirmation page before counting a submission."],
          ].map(([title, description]) => (
            <div key={title} className="py-3 first:pt-0">
              <dt className="font-semibold">{title}</dt>
              <dd className="mt-1 leading-relaxed text-muted-foreground">{description}</dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-border pt-4 text-sm">
          {[
            ["Explore Browserbase", "https://www.browserbase.com/"],
            ["Explore Stagehand", "https://docs.stagehand.dev/"],
            ["Saved Contexts", "https://docs.browserbase.com/platform/browser/core-features/contexts"],
            ["CAPTCHA support", "https://docs.browserbase.com/platform/identity/captcha-solving"],
          ].map(([label, href]) => (
            <a key={href} href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-blue-700 underline underline-offset-4 focus-visible:outline focus-visible:outline-2 dark:text-blue-300">
              {label}<ExternalLink className="h-3 w-3" aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span>
            </a>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
