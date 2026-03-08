// Copyright (c) 2026 V2 Software LLC. All rights reserved.

export { MarketingAgent } from './agent';
export { copyGeneratorTool } from './tools/copy-generator';
export { copyReviewerTool } from './tools/copy-reviewer';
export { HubSpotIntegration } from './integrations/hubspot';
export { AnalyticsIntegration } from './integrations/analytics';
export { MARKETING_SYSTEM_PROMPT, COPY_REVIEW_PROMPT, FRAMEWORKS } from './prompts/marketing';
export type { CopyContext, GeneratedCopy, CopyReview, CopyIssue, MarketingAgentOptions } from './agent';
export type {
  EmailCopyPayload,
  LandingPageCopyPayload,
  CopyPerformanceMetrics,
} from './integrations/hubspot';
export type {
  AnalyticsConfig,
  AnalyticsProvider,
  VariantMetrics,
  TopPerformingResult,
  ConversionEvent,
} from './integrations/analytics';
