// Copyright (c) 2026 V2 Software LLC. All rights reserved.

/**
 * Vercel AI SDK tool definition for generating marketing copy.
 *
 * This tool can be plugged into any AI agent built with the Vercel AI SDK.
 * It validates inputs with Zod and delegates to the MarketingAgent.
 */

import { tool } from 'ai';
import { z } from 'zod';
import { MarketingAgent } from '../agent';
import type { CopyContext } from '../agent';

const pageTypes = ['landing', 'pricing', 'feature', 'email'] as const;

export const copyGeneratorTool = tool({
  description:
    'Generate high-quality marketing copy for a product. Supports landing pages, pricing pages, feature pages, and emails. Uses proven copywriting frameworks (AIDA, PAS) to produce conversion-focused content.',
  parameters: z.object({
    product: z
      .string()
      .min(1)
      .describe('A clear description of the product or service.'),
    audience: z
      .string()
      .min(1)
      .describe(
        'Description of the target audience (e.g. "SaaS founders with 10-50 employees").',
      ),
    pageType: z
      .enum(pageTypes)
      .describe('The type of page the copy is for.'),
    tone: z
      .string()
      .default('professional')
      .describe(
        'Desired tone of the copy (e.g. "professional", "playful", "urgent").',
      ),
    keyBenefits: z
      .array(z.string())
      .optional()
      .describe('Key benefits to highlight in the copy.'),
    constraints: z
      .array(z.string())
      .optional()
      .describe('Additional constraints or requirements.'),
  }),

  execute: async ({
    product,
    audience,
    pageType,
    tone,
    keyBenefits,
    constraints,
  }) => {
    const agent = new MarketingAgent();

    const allConstraints: string[] = [];
    if (keyBenefits && keyBenefits.length > 0) {
      allConstraints.push(
        `Highlight these key benefits: ${keyBenefits.join(', ')}`,
      );
    }
    if (constraints) {
      allConstraints.push(...constraints);
    }

    const context: CopyContext = {
      product,
      audience,
      tone,
      pageType,
      constraints: allConstraints.length > 0 ? allConstraints : undefined,
    };

    const result = await agent.generateCopy(context);

    return {
      success: true,
      copy: result,
    };
  },
});
