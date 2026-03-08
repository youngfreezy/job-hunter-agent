// Copyright (c) 2026 V2 Software LLC. All rights reserved.

/**
 * Core marketing agent powered by the Vercel AI SDK and Anthropic Claude.
 *
 * Provides methods for generating, reviewing, and A/B-testing marketing copy.
 */

import { generateText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import {
  MARKETING_SYSTEM_PROMPT,
  COPY_REVIEW_PROMPT,
  FRAMEWORKS,
} from './prompts/marketing';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CopyContext {
  /** Name or short description of the product. */
  product: string;
  /** Target audience description. */
  audience: string;
  /** Desired tone (e.g. "professional", "playful", "urgent"). */
  tone: string;
  /** Type of page the copy is for. */
  pageType: 'landing' | 'pricing' | 'feature' | 'email';
  /** Optional additional constraints or instructions. */
  constraints?: string[];
}

export interface GeneratedCopy {
  headline: string;
  subheadline: string;
  body: string;
  cta: string;
  metadata: {
    framework: string;
    readabilityScore: number;
  };
}

export interface CopyIssue {
  severity: 'high' | 'medium' | 'low';
  type: string;
  description: string;
  location: string;
}

export interface CopyReview {
  score: number;
  issues: CopyIssue[];
  suggestions: string[];
  rewrite: string;
}

// ---------------------------------------------------------------------------
// Agent Options
// ---------------------------------------------------------------------------

export interface MarketingAgentOptions {
  /** Anthropic model to use. Defaults to "claude-sonnet-4-20250514". */
  model?: string;
  /** Maximum tokens for generation. Defaults to 4096. */
  maxTokens?: number;
}

// ---------------------------------------------------------------------------
// MarketingAgent
// ---------------------------------------------------------------------------

export class MarketingAgent {
  private model: string;
  private maxTokens: number;

  constructor(options: MarketingAgentOptions = {}) {
    this.model = options.model ?? 'claude-sonnet-4-20250514';
    this.maxTokens = options.maxTokens ?? 4096;
  }

  // -------------------------------------------------------------------------
  // generateCopy
  // -------------------------------------------------------------------------

  /**
   * Generate new marketing copy for the given product / audience / page type.
   */
  async generateCopy(context: CopyContext): Promise<GeneratedCopy> {
    const framework = this.pickFramework(context);
    const frameworkDetail = JSON.stringify(
      FRAMEWORKS[framework as keyof typeof FRAMEWORKS],
      null,
      2,
    );

    const constraintBlock =
      context.constraints && context.constraints.length > 0
        ? `\nAdditional constraints:\n${context.constraints.map((c) => `- ${c}`).join('\n')}`
        : '';

    const prompt = `
Generate marketing copy for the following context:

Product: ${context.product}
Target audience: ${context.audience}
Tone: ${context.tone}
Page type: ${context.pageType}
Framework to use: ${framework}
${constraintBlock}

Framework details:
${frameworkDetail}

Respond with ONLY valid JSON matching this exact shape (no markdown fences):
{
  "headline": "string",
  "subheadline": "string",
  "body": "string (can contain newlines)",
  "cta": "string",
  "metadata": {
    "framework": "${framework}",
    "readabilityScore": <number 1-100, estimated Flesch-Kincaid readability>
  }
}
`.trim();

    const { text } = await generateText({
      model: anthropic(this.model),
      system: MARKETING_SYSTEM_PROMPT,
      prompt,
      maxTokens: this.maxTokens,
    });

    return this.parseJSON<GeneratedCopy>(text, 'generateCopy');
  }

  // -------------------------------------------------------------------------
  // reviewCopy
  // -------------------------------------------------------------------------

  /**
   * Review existing copy and return a score, issues, suggestions, and a
   * rewrite that addresses all found problems.
   */
  async reviewCopy(copy: string, context: CopyContext): Promise<CopyReview> {
    const prompt = `
Review the following marketing copy and provide detailed feedback.

--- COPY START ---
${copy}
--- COPY END ---

Context:
- Product: ${context.product}
- Audience: ${context.audience}
- Tone: ${context.tone}
- Page type: ${context.pageType}

Respond with ONLY valid JSON matching this exact shape (no markdown fences):
{
  "score": <overall score 1-100>,
  "issues": [
    {
      "severity": "high" | "medium" | "low",
      "type": "string (e.g. passive_voice, jargon, weak_cta, missing_benefit, too_long, unclear_value_prop)",
      "description": "string",
      "location": "string (quote the problematic text)"
    }
  ],
  "suggestions": ["string"],
  "rewrite": "string (full improved version of the copy)"
}
`.trim();

    const { text } = await generateText({
      model: anthropic(this.model),
      system: COPY_REVIEW_PROMPT,
      prompt,
      maxTokens: this.maxTokens,
      temperature: 0,
    });

    return this.parseJSON<CopyReview>(text, 'reviewCopy');
  }

  // -------------------------------------------------------------------------
  // generateVariants
  // -------------------------------------------------------------------------

  /**
   * Generate A/B test variants of a given piece of copy.
   *
   * @param copy    The original copy to generate variants of.
   * @param count   Number of variants to produce (default 3).
   * @returns       An array of variant strings.
   */
  async generateVariants(copy: string, count = 3): Promise<string[]> {
    const prompt = `
You are given the following marketing copy:

--- COPY START ---
${copy}
--- COPY END ---

Generate exactly ${count} distinct A/B test variants of this copy.
Each variant should take a meaningfully different angle, tone, or structure
while preserving the core message and value proposition.

Respond with ONLY a valid JSON array of strings (no markdown fences):
["variant 1 text", "variant 2 text", ...]
`.trim();

    const { text } = await generateText({
      model: anthropic(this.model),
      system: MARKETING_SYSTEM_PROMPT,
      prompt,
      maxTokens: this.maxTokens * count,
    });

    return this.parseJSON<string[]>(text, 'generateVariants');
  }

  // -------------------------------------------------------------------------
  // Private helpers
  // -------------------------------------------------------------------------

  /**
   * Choose the best framework for the given context.
   *
   * PAS works well for problem-aware audiences (feature pages, emails).
   * AIDA works well for top-of-funnel pages (landing, pricing).
   */
  private pickFramework(context: CopyContext): string {
    if (context.pageType === 'feature' || context.pageType === 'email') {
      return 'PAS';
    }
    return 'AIDA';
  }

  /**
   * Safely parse a JSON string returned by the model. Strips markdown code
   * fences if the model included them despite instructions.
   */
  private parseJSON<T>(raw: string, method: string): T {
    let cleaned = raw.trim();

    // Strip markdown code fences
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.replace(/^```(?:json)?\s*/, '').replace(/\s*```$/, '');
    }

    try {
      return JSON.parse(cleaned) as T;
    } catch (error) {
      throw new Error(
        `MarketingAgent.${method}: Failed to parse model response as JSON.\n` +
          `Raw response:\n${raw}\n\n` +
          `Parse error: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }
}
