/**
 * Vercel AI SDK tool definition for reviewing and scoring marketing copy.
 *
 * Evaluates copy across five dimensions and flags specific issues with
 * actionable suggestions for improvement.
 */

import { tool } from 'ai';
import { z } from 'zod';
import { MarketingAgent } from '../agent';
import type { CopyContext } from '../agent';

const pageTypes = ['landing', 'pricing', 'feature', 'email'] as const;

export const copyReviewerTool = tool({
  description:
    'Review and score existing marketing copy. Evaluates clarity, persuasiveness, readability, jargon usage, and CTA strength. Returns a detailed score, a list of issues, suggestions, and a full rewrite.',
  parameters: z.object({
    copy: z
      .string()
      .min(1)
      .describe('The marketing copy to review.'),
    product: z
      .string()
      .min(1)
      .describe('A clear description of the product or service.'),
    audience: z
      .string()
      .min(1)
      .describe('Description of the target audience.'),
    pageType: z
      .enum(pageTypes)
      .describe('The type of page the copy is for.'),
    tone: z
      .string()
      .default('professional')
      .describe('The intended tone of the copy.'),
  }),

  execute: async ({ copy, product, audience, pageType, tone }) => {
    const agent = new MarketingAgent();

    const context: CopyContext = {
      product,
      audience,
      tone,
      pageType,
    };

    const review = await agent.reviewCopy(copy, context);

    return {
      success: true,
      review: {
        overallScore: review.score,
        issues: review.issues,
        suggestions: review.suggestions,
        rewrite: review.rewrite,
      },
    };
  },
});
