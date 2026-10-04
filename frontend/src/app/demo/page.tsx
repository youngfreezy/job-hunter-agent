import type { Metadata } from "next";
import Link from "next/link";
import { DemoVideo } from "@/components/demo/DemoVideo";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Product Demo",
  description: "Watch JobHunter Agent work with Browserbase and Stagehand: an Indeed application workflow with saved authentication, application checks, and model spending controls.",
  alternates: { canonical: "/demo" },
  openGraph: {
    title: "JobHunter Agent — Product Demo",
    description: "A closer look at the application, its cloud browser, and the controls behind each run.",
    url: "/demo",
    images: [{ url: "/media/jobhunter-browserbase-demo-v2.webp", width: 1920, height: 1080, alt: "JobHunter Agent product demo" }],
  },
};

export default function DemoPage() {
  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950 dark:bg-zinc-950 dark:text-white">
      <nav aria-label="Main navigation" className="border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
          <Link href="/" className="rounded text-lg font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4">
            JobHunter Agent
          </Link>
          <Button asChild variant="outline" size="sm"><Link href="/auth/login">Log in</Link></Button>
        </div>
      </nav>
      <main className="mx-auto max-w-6xl px-6 py-10 md:py-16">
        <header className="mb-8 max-w-3xl">
          <p className="mb-3 text-sm font-medium text-zinc-600 dark:text-zinc-400">Product walkthrough</p>
          <h1 className="text-3xl font-bold tracking-tight md:text-5xl">See JobHunter Agent in action.</h1>
          <p id="demo-description" className="mt-4 text-lg leading-relaxed text-zinc-600 dark:text-zinc-400">
            Follow an Indeed application workflow and see how Browserbase, Stagehand,
            and the app&apos;s checks work together.
          </p>
        </header>
        <DemoVideo />
        <section aria-labelledby="walkthrough-heading" className="mt-10 border-t border-zinc-200 pt-8 dark:border-zinc-800">
          <h2 id="walkthrough-heading" className="text-xl font-semibold">Inside the demo</h2>
          <ol className="mt-5 grid gap-6 text-sm leading-relaxed text-zinc-600 md:grid-cols-3 dark:text-zinc-400">
            <li><h3 className="mb-1 font-semibold text-zinc-900 dark:text-white">1. Start with your search</h3>Set role preferences and supply a resume. The app uses those facts to guide the application workflow.</li>
            <li><h3 className="mb-1 font-semibold text-zinc-900 dark:text-white">2. See the browser at work</h3><a href="https://www.browserbase.com/" className="underline underline-offset-4">Browserbase</a> runs the cloud browser with saved login context. <a href="https://www.stagehand.dev/" className="underline underline-offset-4">Stagehand</a> interprets pages and performs browser actions.</li>
            <li><h3 className="mb-1 font-semibold text-zinc-900 dark:text-white">3. Check the outcome and cost</h3>The app checks submission evidence and reserves model spending before dispatch. Unknown usage stays held; Browserbase billing is separate.</li>
          </ol>
        </section>
        <div className="mt-10 flex flex-wrap items-center gap-4">
          <Button asChild><Link href="/session/new">Start a job search</Link></Button>
          <Link href="/" className="rounded text-sm text-zinc-600 underline underline-offset-4 hover:text-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 dark:text-zinc-400 dark:hover:text-white">Back to the product</Link>
        </div>
      </main>
    </div>
  );
}
