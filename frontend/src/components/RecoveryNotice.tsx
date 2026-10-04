"use client";

import { Button } from "@/components/ui/button";

export function RecoveryNotice({ message, onRetry, retryLabel = "Reload" }: {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return <div role="alert" className="my-4 rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm">
    <p>{message}</p>
    <Button className="mt-3" size="sm" variant="outline" onClick={onRetry || (() => window.location.reload())}>{retryLabel}</Button>
  </div>;
}
