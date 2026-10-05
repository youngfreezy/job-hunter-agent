"use client";

import { useState } from "react";

const videoUrl = "/media/jobhunter-browserbase-demo-v3.mp4";

export function DemoVideo() {
  const [failed, setFailed] = useState(false);

  return (
    <div>
      <video
        controls
        playsInline
        preload="none"
        poster="/media/jobhunter-browserbase-demo-v3.jpg"
        aria-label="JobHunter Agent product demo"
        aria-describedby="demo-description"
        className="aspect-video w-full rounded-xl border border-zinc-200 bg-zinc-950 dark:border-zinc-800"
        onError={() => setFailed(true)}
      >
        <source src={videoUrl} type="video/mp4" />
        Your browser does not support embedded video. Open the video using the link below.
      </video>
      {failed && (
        <p role="status" className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
          The video could not load. Try opening it directly, or read the walkthrough below.
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-zinc-600 dark:text-zinc-400">
        <p>Recorded application workflow and Browserbase session replay. Sound is optional.</p>
        <a href={videoUrl} className="rounded underline underline-offset-4 hover:text-zinc-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 dark:hover:text-white">
          Open video directly
        </a>
      </div>
    </div>
  );
}
