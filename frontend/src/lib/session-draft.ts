import { sessionInitialValues, type SessionFormValues } from "./schemas/session";
import { clampMaxJobs } from "./quick-start-config";

/** Restore editable user preferences, never a previous upload's server identity. */
export function restoreSessionDraft(value: unknown): SessionFormValues {
  const defaults = sessionInitialValues;
  if (!value || typeof value !== "object" || Array.isArray(value)) return { ...defaults };
  const draft = value as Record<string, unknown>;
  const text = (key: keyof SessionFormValues): string => typeof draft[key] === "string" ? draft[key] : "";
  const maxJobs = typeof draft.maxJobs === "number" && Number.isFinite(draft.maxJobs)
    ? clampMaxJobs(Math.floor(draft.maxJobs)) : defaults.maxJobs;
  const minimum = typeof draft.minimumSubmittedApplications === "number" && Number.isFinite(draft.minimumSubmittedApplications)
    ? Math.min(maxJobs, Math.max(0, Math.floor(draft.minimumSubmittedApplications))) : 0;
  return {
    ...defaults,
    discoveryPrompt: text("discoveryPrompt"),
    keywords: text("keywords"),
    locations: text("locations"),
    salaryMin: text("salaryMin"),
    resumeText: text("resumeText"),
    resumeFileName: text("resumeFileName"),
    linkedinUrl: text("linkedinUrl"),
    remoteOnly: typeof draft.remoteOnly === "boolean" ? draft.remoteOnly : defaults.remoteOnly,
    searchRadius: typeof draft.searchRadius === "number" && [10, 25, 50, 100, 150, 200].includes(draft.searchRadius)
      ? draft.searchRadius : defaults.searchRadius,
    maxJobs,
    minimumSubmittedApplications: minimum,
    tailoringQuality: draft.tailoringQuality === "premium" ? "premium" : defaults.tailoringQuality,
    applicationMode: draft.applicationMode === "materials_only" ? "materials_only" : defaults.applicationMode,
    generateCoverLetters: typeof draft.generateCoverLetters === "boolean" ? draft.generateCoverLetters : defaults.generateCoverLetters,
    jobBoards: Array.isArray(draft.jobBoards) && draft.jobBoards.every((board): board is string => typeof board === "string")
      ? [...draft.jobBoards] : [...defaults.jobBoards],
  };
}
