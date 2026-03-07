"use client";

import { useFormikContext } from "formik";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SessionFormValues } from "@/lib/schemas/session";

const BOARDS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "indeed", label: "Indeed" },
  { id: "glassdoor", label: "Glassdoor" },
  { id: "ziprecruiter", label: "ZipRecruiter" },
];

const COST_ESTIMATES: Record<string, number> = {
  "auto_apply+standard": 80,
  "auto_apply+premium": 100,
  "materials_only+standard": 50,
  "materials_only+premium": 60,
};

function estimateCredits(values: SessionFormValues): number {
  const key = `${values.applicationMode}+${values.tailoringQuality}`;
  const base = COST_ESTIMATES[key] ?? 80;
  const jobRatio = (values.maxJobs ?? 20) / 20;
  return Math.round(base * jobRatio);
}

export function ConfigStep() {
  const { values, setFieldValue } = useFormikContext<SessionFormValues>();

  const boards = values.jobBoards ?? ["linkedin", "indeed", "glassdoor", "ziprecruiter"];
  const credits = estimateCredits(values);

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Session Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Max Jobs */}
          <div>
            <label className="text-sm font-medium">
              Maximum jobs to process: <span className="text-blue-600 font-bold">{values.maxJobs ?? 20}</span>
            </label>
            <input
              type="range"
              min={5}
              max={50}
              step={5}
              value={values.maxJobs ?? 20}
              onChange={(e) => setFieldValue("maxJobs", parseInt(e.target.value))}
              className="w-full mt-2 accent-blue-600"
            />
            <div className="flex justify-between text-xs text-zinc-400 mt-1">
              <span>5</span>
              <span>25</span>
              <span>50</span>
            </div>
          </div>

          {/* Tailoring Quality */}
          <div>
            <label className="text-sm font-medium mb-2 block">Resume tailoring quality</label>
            <div className="grid grid-cols-2 gap-3">
              {([
                { value: "standard", label: "Standard", desc: "Fast and cost-effective" },
                { value: "premium", label: "Premium", desc: "Top-tier model for best 20%" },
              ] as const).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setFieldValue("tailoringQuality", opt.value)}
                  className={`rounded-xl border p-4 text-left transition-all ${
                    values.tailoringQuality === opt.value
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
                      : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-800"
                  }`}
                >
                  <p className="text-sm font-medium">{opt.label}</p>
                  <p className="text-xs text-zinc-500 mt-1">{opt.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Application Mode */}
          <div>
            <label className="text-sm font-medium mb-2 block">Application mode</label>
            <div className="grid grid-cols-2 gap-3">
              {([
                { value: "auto_apply", label: "Auto Apply", desc: "Browser automation submits forms" },
                { value: "materials_only", label: "Materials Only", desc: "Generate resumes & cover letters only" },
              ] as const).map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setFieldValue("applicationMode", opt.value)}
                  className={`rounded-xl border p-4 text-left transition-all ${
                    values.applicationMode === opt.value
                      ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
                      : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-800"
                  }`}
                >
                  <p className="text-sm font-medium">{opt.label}</p>
                  <p className="text-xs text-zinc-500 mt-1">{opt.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Cover Letters */}
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="generateCoverLetters"
              checked={values.generateCoverLetters ?? true}
              onChange={(e) => setFieldValue("generateCoverLetters", e.target.checked)}
              className="h-4 w-4 rounded accent-blue-600"
            />
            <label htmlFor="generateCoverLetters" className="text-sm">
              Generate cover letters for each job
            </label>
          </div>

          {/* Job Boards */}
          <div>
            <label className="text-sm font-medium mb-2 block">Job boards to search</label>
            <div className="flex flex-wrap gap-2">
              {BOARDS.map((board) => {
                const active = boards.includes(board.id);
                return (
                  <button
                    key={board.id}
                    type="button"
                    onClick={() => {
                      const next = active
                        ? boards.filter((b: string) => b !== board.id)
                        : [...boards, board.id];
                      if (next.length > 0) setFieldValue("jobBoards", next);
                    }}
                    className={`rounded-full px-4 py-1.5 text-sm border transition-all ${
                      active
                        ? "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-950/30 dark:text-blue-300"
                        : "border-zinc-200 text-zinc-500 hover:border-zinc-300 dark:border-zinc-700"
                    }`}
                  >
                    {board.label}
                  </button>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Cost Estimate */}
      <Card className="border-green-200 bg-green-50/60 dark:border-green-900 dark:bg-green-950/20">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-zinc-600 dark:text-zinc-400">Estimated cost</p>
              <p className="text-xs text-zinc-500 mt-1">Based on your configuration</p>
            </div>
            <div className="text-right">
              <p className="text-2xl font-bold text-green-700 dark:text-green-400">
                ~{credits} credits
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
