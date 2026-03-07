# @jobhunter/marketing-agent

Standalone AI marketing agent for generating and optimizing copy. Uses the [Vercel AI SDK](https://sdk.vercel.ai/) with Claude to produce conversion-focused marketing content, with integrations for HubSpot and analytics platforms.

## Features

- Generate marketing copy for landing pages, pricing pages, feature pages, and emails
- Review and score existing copy with actionable feedback
- Generate A/B test variants
- Built-in copywriting frameworks (AIDA, PAS)
- HubSpot integration for pushing copy to emails and landing pages
- Analytics integration (Mixpanel, GA4, Segment, or custom)
- CLI for quick testing

## Quick Start

### Install

```bash
npm install @jobhunter/marketing-agent
```

### Set your API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Generate copy

```typescript
import { MarketingAgent } from '@jobhunter/marketing-agent';

const agent = new MarketingAgent();

const copy = await agent.generateCopy({
  product: 'ProjectFlow - AI-powered project management for remote teams',
  audience: 'Engineering managers at Series A-C startups',
  tone: 'confident',
  pageType: 'landing',
  constraints: ['Mention the free trial', 'Keep headline under 8 words'],
});

console.log(copy.headline);     // e.g. "Ship Faster With Less Chaos"
console.log(copy.subheadline);  // e.g. "AI keeps your remote team aligned..."
console.log(copy.cta);          // e.g. "Start your free 14-day trial"
```

### Review existing copy

```typescript
const review = await agent.reviewCopy(
  'Our synergistic platform leverages cutting-edge AI to optimize your workflow.',
  {
    product: 'ProjectFlow',
    audience: 'Engineering managers',
    tone: 'professional',
    pageType: 'landing',
  },
);

console.log(review.score);       // e.g. 35
console.log(review.issues);      // [{severity: 'high', type: 'jargon', ...}]
console.log(review.rewrite);     // Improved version
```

### Generate A/B test variants

```typescript
const variants = await agent.generateVariants(
  'Ship 3x faster with AI project management. Start free.',
  3,
);
// Returns 3 distinct variants of the copy
```

## CLI Usage

```bash
# Generate copy
npx tsx src/cli.ts generate \
  --product "ProjectFlow - AI project management" \
  --audience "Engineering managers" \
  --pageType landing \
  --tone confident

# Review copy from a file
npx tsx src/cli.ts review \
  --file landing-page.txt \
  --product "ProjectFlow" \
  --audience "Engineering managers"

# Review copy from stdin
echo "Buy now! Best tool ever!" | npx tsx src/cli.ts review \
  --product "ProjectFlow" \
  --audience "Engineering managers"
```

## API Reference

### `MarketingAgent`

The core agent class.

```typescript
const agent = new MarketingAgent({
  model: 'claude-sonnet-4-20250514',  // optional, defaults to claude-sonnet-4-20250514
  maxTokens: 2048,                    // optional, defaults to 2048
});
```

#### `generateCopy(context: CopyContext): Promise<GeneratedCopy>`

Generate new marketing copy.

#### `reviewCopy(copy: string, context: CopyContext): Promise<CopyReview>`

Review existing copy and get a score, issues, suggestions, and rewrite.

#### `generateVariants(copy: string, count?: number): Promise<string[]>`

Generate A/B test variants of existing copy.

### Types

```typescript
interface CopyContext {
  product: string;
  audience: string;
  tone: string;
  pageType: 'landing' | 'pricing' | 'feature' | 'email';
  constraints?: string[];
}

interface GeneratedCopy {
  headline: string;
  subheadline: string;
  body: string;
  cta: string;
  metadata: { framework: string; readabilityScore: number };
}

interface CopyReview {
  score: number;
  issues: CopyIssue[];
  suggestions: string[];
  rewrite: string;
}

interface CopyIssue {
  severity: 'high' | 'medium' | 'low';
  type: string;
  description: string;
  location: string;
}
```

### Vercel AI SDK Tools

Use these tools in any Vercel AI SDK agent:

```typescript
import { copyGeneratorTool, copyReviewerTool } from '@jobhunter/marketing-agent';
import { generateText } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';

const result = await generateText({
  model: anthropic('claude-sonnet-4-20250514'),
  tools: { generateCopy: copyGeneratorTool, reviewCopy: copyReviewerTool },
  prompt: 'Generate a landing page for our new analytics product...',
});
```

## Integrations

### HubSpot

Push generated copy directly to HubSpot emails and landing pages.

```typescript
import { HubSpotIntegration } from '@jobhunter/marketing-agent';

const hubspot = new HubSpotIntegration('your-hubspot-access-token');

// Push to an email campaign
await hubspot.pushToEmail(
  { subject: copy.headline, body: copy.body },
  'campaign-id',
);

// Push to a landing page
await hubspot.pushToLandingPage(
  { headline: copy.headline, subheadline: copy.subheadline, body: copy.body, cta: copy.cta },
  'page-id',
);

// Track performance
const metrics = await hubspot.trackCopyPerformance('content-id');
```

### Analytics

Track copy variant performance with Mixpanel, GA4, Segment, or a custom backend.

```typescript
import { AnalyticsIntegration } from '@jobhunter/marketing-agent';

const analytics = new AnalyticsIntegration({
  provider: 'mixpanel',
  apiKey: 'your-mixpanel-token',
});

// Track variant metrics
await analytics.trackCopyVariant('variant-a', {
  impressions: 1200,
  clicks: 85,
  conversions: 12,
});

// Get top performers
const top = await analytics.getTopPerforming('landing');

// Report a conversion
await analytics.reportConversion('copy-id', 'signup', 49.99);
```

## Marketing Frameworks

The agent uses two proven copywriting frameworks, automatically selecting the best one based on context:

### AIDA (Attention, Interest, Desire, Action)

Used for top-of-funnel content like landing pages and pricing pages. Grabs attention with a hook, builds interest, creates desire through benefits and social proof, and drives action with a clear CTA.

### PAS (Problem, Agitation, Solution)

Used for problem-aware audiences like feature pages and emails. Names the problem, amplifies the emotional weight, and presents the product as the solution.

## Using in a Next.js App

```typescript
// app/api/generate-copy/route.ts
import { MarketingAgent } from '@jobhunter/marketing-agent';
import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  const body = await request.json();
  const agent = new MarketingAgent();

  const copy = await agent.generateCopy({
    product: body.product,
    audience: body.audience,
    tone: body.tone ?? 'professional',
    pageType: body.pageType ?? 'landing',
  });

  return NextResponse.json(copy);
}
```

## License

MIT
