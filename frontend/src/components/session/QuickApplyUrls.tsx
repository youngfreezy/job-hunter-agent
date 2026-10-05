"use client";
import { useState } from "react";

export function QuickApplyUrls({
  urls,
  submitted,
  failed,
}: {
  urls: string[];
  submitted: number;
  failed: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const processed = submitted + failed;
  const total = urls.length;

  function hostLabel(url: string) {
    try {
      const h = new URL(url).hostname.replace("www.", "");
      // Show a short recognizable label
      if(h.includes("greenhouse")) return "Greenhouse";
      if(h.includes("lever")) return "Lever";
      if(h.includes("ashby")) return "Ashby";
      if(h.includes("workday")) return "Workday";
      if(h.includes("linkedin")) return "LinkedIn";
      if(h.includes("deloitte")) return "Deloitte";
      if(h.includes("aplitrak")) return "Aplitrak";
      return h.split(".")[0];
    } catch {
      return url.slice(0, 30);
    }
  }

  return (
    <div className="border-t border-border/30 pt-2">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center justify-between text-xs"
      >
        <span className="uppercase tracking-wider text-muted-foreground">
          Quick Apply
        </span>
        <span className="flex items-center gap-1.5 font-medium">
          <span className="text-blue-600 dark:text-blue-400">
            {processed}/{total}
          </span>
          <svg
            className={`h-3 w-3 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </button>

      {/* Progress bar */}
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500"
          style={{ width: `${total > 0 ? (processed / total) * 100 : 0}%` }}
        />
      </div>

      {expanded && (
        <ul className="mt-2 space-y-1">
          {urls.map((url, i) => (
            <li key={i} className="flex items-center gap-1.5 text-xs">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-600" />
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-blue-600 hover:underline dark:text-blue-400"
                title={url}
              >
                {hostLabel(url)}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
