"use client";

import { useEffect, useState } from "react";
import { loadSessionScreenshot } from "@/lib/screenshot";

export function SessionScreenshot({ sessionId, path, alt }: { sessionId: string; path: string; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setSrc(null);
    setError("");
    loadSessionScreenshot(sessionId, path, controller.signal).then((blob) => {
      if (controller.signal.aborted) return;
      objectUrl = URL.createObjectURL(blob);
      setSrc(objectUrl);
    }).catch((cause) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Could not load screenshot.");
    });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [sessionId, path, attempt]);
  if (error) return <div role="alert" className="p-4 text-sm"><p>{error}</p><button type="button" onClick={() => setAttempt((value) => value + 1)} className="mt-2 underline">Retry screenshot</button></div>;
  if (!src) return <p role="status" className="p-4 text-sm text-muted-foreground">Loading screenshot…</p>;
  // Blob URL was fetched with the current account's Authorization header.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt={alt} className="w-full" />;
}
