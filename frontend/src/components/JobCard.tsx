// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

interface Job {
  id: string;
  title: string;
  company: string;
  location: string;
  url: string;
  board: string;
  salary_range?: string | null;
  is_remote?: boolean;
}

interface JobCardProps {
  job: Job;
  score: number;
  breakdown?: Record<string, number>;
  selected?: boolean;
  onToggle?: (id: string) => void;
  compact?: boolean;
}

export function JobCard({ job, score, breakdown, selected, onToggle, compact }: JobCardProps) {
  const scoreColor =
    score >= 80
      ? "bg-green-100 text-green-800"
      : score >= 60
      ? "bg-yellow-100 text-yellow-800"
      : "bg-red-100 text-red-800";

  if (compact) {
    return (
      <div
        className={`border rounded p-2 text-xs cursor-pointer transition-colors ${
          selected
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
            : "hover:bg-zinc-50 dark:hover:bg-zinc-900"
        }`}
        onClick={() => onToggle?.(job.id)}
      >
        <div className="flex items-center justify-between">
          <span className="font-medium truncate">{job.title}</span>
          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${scoreColor}`}>{score}</span>
        </div>
        <p className="text-zinc-500 truncate">
          {job.company} — {job.location}
        </p>
      </div>
    );
  }

  return (
    <Card className={selected ? "border-blue-500" : ""}>
      <CardContent className="py-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-medium text-sm truncate">{job.title}</h3>
              {job.is_remote && (
                <Badge variant="secondary" className="text-xs">
                  Remote
                </Badge>
              )}
            </div>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">{job.company}</p>
            <p className="text-xs text-zinc-500">{job.location}</p>
            {job.salary_range && <p className="text-xs text-green-600 mt-1">{job.salary_range}</p>}
            <div className="flex gap-1 mt-2">
              <Badge variant="outline" className="text-xs">
                {job.board}
              </Badge>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2 ml-3">
            <div className={`px-2 py-1 rounded text-sm font-bold ${scoreColor}`}>{score}/100</div>
            {onToggle && (
              <Button
                size="sm"
                variant={selected ? "default" : "outline"}
                onClick={() => onToggle(job.id)}
                className="text-xs"
              >
                {selected ? "Selected" : "Select"}
              </Button>
            )}
          </div>
        </div>
        {breakdown && (
          <div className="flex gap-3 mt-2 text-xs text-zinc-500">
            {Object.entries(breakdown).map(([key, val]) => (
              <span key={key}>
                {key.replace(/_/g, " ")}: {val}%
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
