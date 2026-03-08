// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface HealthCheck {
  status: "ok" | "degraded" | "error";
  checks?: {
    postgres?: string;
    redis?: string;
  };
  version?: string;
}

export default function StatusPage() {
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [error, setError] = useState(false);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  useEffect(() => {
    async function check() {
      try {
        const res = await fetch(`${API_BASE}/api/health/ready`, { cache: "no-store" });
        const data = await res.json();
        setHealth(data);
        setError(false);
      } catch {
        setError(true);
        setHealth(null);
      }
      setLastChecked(new Date());
    }
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  const overall = error ? "outage" : health?.status === "ok" ? "operational" : "degraded";

  const services = [
    { name: "API Gateway", status: error ? "unavailable" : "operational" },
    { name: "PostgreSQL Database", status: error ? "unavailable" : health?.checks?.postgres === "ok" ? "operational" : "unavailable" },
    { name: "Redis Cache", status: error ? "unavailable" : health?.checks?.redis === "ok" ? "operational" : "unavailable" },
  ];

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-950 dark:bg-zinc-950 dark:text-white">
      <nav className="border-b border-zinc-200/80 bg-white/80 px-6 py-4 backdrop-blur-md dark:border-zinc-800 dark:bg-zinc-950/80">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <Link href="/" className="text-xl font-bold tracking-tight">JobHunter Agent</Link>
          <Link href="/">
            <Button variant="outline" size="sm">Back to Home</Button>
          </Link>
        </div>
      </nav>

      <div className="mx-auto max-w-4xl px-6 py-16">
        <h1 className="text-3xl font-bold mb-2">System Status</h1>
        <p className="text-zinc-500 dark:text-zinc-400 mb-10">Real-time health of JobHunter Agent services. This page auto-refreshes every 30 seconds.</p>

        {/* Overall status */}
        <Card className="rounded-2xl mb-8">
          <CardContent className="flex items-center gap-4 py-6">
            <div className={`h-4 w-4 rounded-full ${overall === "operational" ? "bg-emerald-500" : overall === "degraded" ? "bg-yellow-500" : "bg-red-500"}`} />
            <div>
              <p className="font-semibold text-lg">
                {overall === "operational" && "All Systems Operational"}
                {overall === "degraded" && "Partial Service Degradation"}
                {overall === "outage" && "Service Disruption Detected"}
              </p>
              {lastChecked && (
                <p className="text-xs text-zinc-500">Last checked: {lastChecked.toLocaleTimeString()}</p>
              )}
            </div>
            {health?.version && <Badge variant="secondary" className="ml-auto">v{health.version}</Badge>}
          </CardContent>
        </Card>

        {/* Individual services */}
        <div className="space-y-3 mb-10">
          {services.map((svc) => (
            <div key={svc.name} className="flex items-center justify-between rounded-xl border border-zinc-200 bg-white px-5 py-4 dark:border-zinc-800 dark:bg-zinc-950">
              <span className="font-medium">{svc.name}</span>
              <Badge variant={svc.status === "operational" ? "secondary" : "destructive"} className={svc.status === "operational" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : ""}>
                {svc.status === "operational" ? "Operational" : "Unavailable"}
              </Badge>
            </div>
          ))}
        </div>

        {/* Uptime commitment */}
        <Card className="rounded-2xl border-blue-200/60 bg-blue-50/50 dark:border-blue-900/40 dark:bg-blue-950/20">
          <CardContent className="py-6 text-center">
            <p className="font-semibold text-zinc-900 dark:text-white">99.9% Uptime SLA</p>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              We monitor all services 24/7 with Sentry error tracking, structured logging, and automated health checks.
              Infrastructure runs on containerized Docker services with PostgreSQL and Redis, designed for automatic failover and horizontal scaling.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
