// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export { MarketingAgent } from './agent.js';
export { copyGeneratorTool } from './tools/copy-generator.js';
export { copyReviewerTool } from './tools/copy-reviewer.js';
export { HubSpotIntegration } from './integrations/hubspot.js';
export { AnalyticsIntegration } from './integrations/analytics.js';
export { MARKETING_SYSTEM_PROMPT, COPY_REVIEW_PROMPT, FRAMEWORKS } from './prompts/marketing.js';
export type { CopyContext, GeneratedCopy, CopyReview, CopyIssue, MarketingAgentOptions } from './agent.js';
export type {
  EmailCopyPayload,
  LandingPageCopyPayload,
  CopyPerformanceMetrics,
} from './integrations/hubspot.js';
export type {
  AnalyticsConfig,
  AnalyticsProvider,
  VariantMetrics,
  TopPerformingResult,
  ConversionEvent,
} from './integrations/analytics.js';
