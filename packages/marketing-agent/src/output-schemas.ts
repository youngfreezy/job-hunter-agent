import { z } from 'zod';

export const generatedCopySchema = z.object({
  headline: z.string(), subheadline: z.string(), body: z.string(), cta: z.string(),
  metadata: z.object({ framework: z.string(), readabilityScore: z.number().min(1).max(100) }),
});

export const copyReviewSchema = z.object({
  score: z.number().min(1).max(100),
  issues: z.array(z.object({
    severity: z.enum(['high', 'medium', 'low']),
    type: z.string(), description: z.string(), location: z.string(),
  })),
  suggestions: z.array(z.string()), rewrite: z.string(),
});

/** Model responses are untrusted; errors must not echo customer copy. */
export function parseModelOutput<T>(raw: string, schema: z.ZodType<T>, operation: string): T {
  const text = raw.trim().replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
  try {
    return schema.parse(JSON.parse(text));
  } catch {
    throw new Error(`MarketingAgent.${operation}: Model response did not match the expected schema.`);
  }
}
