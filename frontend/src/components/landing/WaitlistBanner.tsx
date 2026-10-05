// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Button } from "@/components/ui/button";
import { useCallback, useState } from "react";
import { toast } from "sonner";

export function WaitlistBanner() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    if(!email.trim()) return;
    setStatus("loading");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ""}/api/waitlist`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.trim() }),
        }
      );
      if(res.ok) {
        setStatus("success");
        setEmail("");
        toast.success("You're on the list! We'll notify you when we launch.");
      } else if(res.status === 409) {
        setStatus("success");
        toast.info("You're already on the waitlist!");
      } else {
        const data = await res.json().catch(() => ({}));
        setStatus("error");
        setMessage(data.detail || "Something went wrong. Try again.");
      }
    } catch {
      setStatus("error");
      setMessage("Network error. Try again.");
    }
  }, [email]);

  if(status === "success") return null;

  return (
    <div className="sticky top-0 z-[60] bg-zinc-900 px-4 py-3 text-white">
      <div className="mx-auto flex max-w-7xl flex-col items-center gap-3 sm:flex-row sm:justify-center">
        <p className="text-sm font-medium">
          We&apos;re launching soon &mdash; get early access and 5 free application credits.
        </p>
        {status === "error" ? null : (
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              type="email"
              required
              placeholder="you@email.com"
              value={email}
              onChange={(e) => { setEmail(e.target.value); setStatus("idle"); }}
              className="rounded-md border-0 bg-white/20 px-3 py-1.5 text-sm text-white placeholder-white/70 backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-white/50"
            />
            <Button
              type="submit"
              size="sm"
              disabled={status === "loading"}
              className="bg-white text-orange-700 hover:bg-white/90 font-semibold"
            >
              {status === "loading" ? "..." : "Join Waitlist"}
            </Button>
          </form>
        )}
        {status === "error" && (
          <span className="text-xs text-red-200">{message}</span>
        )}
      </div>
    </div>
  );
}
