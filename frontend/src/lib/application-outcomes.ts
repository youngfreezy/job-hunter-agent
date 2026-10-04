export function applicationOutcomeCounts(
  failures: Array<{ error_category?: string }> = [],
  summary?: { total_failed?: number; total_uncertain?: number } | null,
) {
  const fromResults = failures.filter((result) => result.error_category === 'submission_uncertain').length;
  const uncertain = Math.max(summary?.total_uncertain ?? 0, fromResults);
  // Older summaries included uncertain deliveries in total_failed.
  const failed = summary?.total_failed == null
    ? failures.length - fromResults
    : Math.max(0, summary.total_failed - (typeof summary.total_uncertain === "number" ? 0 : fromResults));
  return { failed, uncertain };
}
