// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export type RunOverrides = {
  keywords: string[];
  locations: string[];
  remote_only: boolean;
  salary_min: number | null;
};

export function AdjustDialog({
  run,
  busy,
  costLine,
  onCancel,
  onStart,
}: {
  run: { keywords?: string[]; locations?: string[]; remote_only?: boolean; salary_min?: number | null };
  busy: boolean;
  costLine: string;
  onCancel: () => void;
  onStart: (o: RunOverrides) => void;
}) {
  const [keywords, setKeywords] = useState((run.keywords ?? []).join(", "));
  const [locations, setLocations] = useState((run.locations ?? []).join(", "));
  const [salary, setSalary] = useState(run.salary_min ? String(run.salary_min) : "");
  const [remote, setRemote] = useState(!!run.remote_only);
  const [error, setError] = useState<string | null>(null);
  const split = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);

  return (
    <Dialog open onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            const kw = split(keywords);
            if (kw.length === 0) {
              setError("Add at least one role.");
              return;
            }
            onStart({
              keywords: kw,
              locations: split(locations),
              remote_only: remote,
              salary_min: salary ? Number(salary.replace(/[^0-9]/g, "")) || null : null,
            });
          }}
        >
          <DialogHeader>
            <DialogTitle>Adjust search</DialogTitle>
            <DialogDescription>
              Starts a new run with these settings. To widen the shortlist, add roles or lower the
              score cutoff in Settings.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <label htmlFor="adj-roles" className="text-sm font-medium">
              Roles
            </label>
            <Input id="adj-roles" value={keywords} onChange={(e) => setKeywords(e.target.value)} aria-describedby="adj-roles-hint adj-error" />
            <p id="adj-roles-hint" className="text-xs text-muted-foreground">
              Separate roles with commas.
            </p>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="adj-places" className="text-sm font-medium">
              Locations
            </label>
            <Input id="adj-places" value={locations} onChange={(e) => setLocations(e.target.value)} disabled={remote} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={remote} onChange={(e) => setRemote(e.target.checked)} className="h-4 w-4 accent-[hsl(var(--primary))]" />
            Remote only
          </label>
          <div className="space-y-1.5">
            <label htmlFor="adj-salary" className="text-sm font-medium">
              Minimum salary
            </label>
            <Input id="adj-salary" inputMode="numeric" value={salary} onChange={(e) => setSalary(e.target.value)} placeholder="Any" className="font-mono" />
          </div>
          <p id="adj-error" role="alert" className="text-sm text-destructive empty:hidden">
            {error}
          </p>
          <p className="text-xs text-muted-foreground">{costLine}</p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button type="submit" loading={busy}>
              Start run
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
