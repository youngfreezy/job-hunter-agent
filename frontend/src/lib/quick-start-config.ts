import type { startSession } from './api';

type SessionConfig = NonNullable<Parameters<typeof startSession>[0]['config']>;

export function clampMaxJobs(count: number): number {
  return Math.min(Math.max(count, 1), 20);
}

/** Premium searches replenish failed attempts toward the selected submission target. */
export function buildQuickStartConfig(
  maxJobs: number,
  isPremium: boolean,
  savedSettings: Record<string, unknown>,
): SessionConfig {
  return {
    max_jobs: maxJobs,
    minimum_submitted_applications: isPremium ? maxJobs : 0,
    tailoring_quality: 'standard',
    application_mode: (savedSettings.application_mode as string) ?? 'auto_apply',
    generate_cover_letters: (savedSettings.generate_cover_letters as boolean) ?? true,
    job_boards: (savedSettings.job_boards as string[]) ?? ['indeed'],
    ai_temperature: (savedSettings.ai_temperature as number) ?? 0.0,
    scoring_strictness: (savedSettings.scoring_strictness as number) ?? 0.5,
  };
}
