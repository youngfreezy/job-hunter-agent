import type { ApplicationLogEntry } from "./api";
export type ApplicationLogStatus = ApplicationLogEntry["status"] | "uncertain";

/** Delivery uncertainty must not become a recommendation to submit twice. */
export function applicationLogStatus(entry: Pick<ApplicationLogEntry, "status" | "error_category">): ApplicationLogStatus {
  return entry.error_category === "submission_uncertain" ? "uncertain" : entry.status;
}
export function applicationLogLabel(entry: Pick<ApplicationLogEntry, "status" | "error_category">): string {
  return applicationLogStatus(entry) === "uncertain" ? "Confirmation pending—check before retrying" : entry.status;
}
