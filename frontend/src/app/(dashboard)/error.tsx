// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect } from "react";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Dashboard error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Something went wrong</h2>
      <p className="text-gray-600 mb-6">
        An unexpected error occurred. Please try again.
      </p>
      <button
        onClick={reset}
        className="rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
      >
        Try again
      </button>
    </div>
  );
}
