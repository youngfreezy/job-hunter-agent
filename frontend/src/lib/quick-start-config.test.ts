import { describe, expect, it } from 'vitest';
import { buildQuickStartConfig } from './quick-start-config';

describe('Quick Start application target', () => {
  it.each([5, 10, 15, 20])('targets %i successful submissions for premium accounts', (count) => {
    const config = buildQuickStartConfig(count, true, { max_jobs: 5, minimum_submitted_applications: 2 });
    expect(config.max_jobs).toBe(count);
    expect(config.minimum_submitted_applications).toBe(count);
  });

  it('does not request premium retries for a non-premium account', () => {
    const config = buildQuickStartConfig(20, false, { minimum_submitted_applications: 20 });
    expect(config.max_jobs).toBe(20);
    expect(config.minimum_submitted_applications).toBe(0);
  });

  it('preserves the saved application settings alongside the target', () => {
    const config = buildQuickStartConfig(15, true, {
      generate_cover_letters: false, scoring_strictness: 0.8, ai_temperature: 0.2,
    });
    expect(config).toMatchObject({
      max_jobs: 15, minimum_submitted_applications: 15,
      generate_cover_letters: false, scoring_strictness: 0.8, ai_temperature: 0.2,
      job_boards: ['indeed'], application_mode: 'auto_apply', tailoring_quality: 'standard',
    });
  });
});
