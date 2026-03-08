// Copyright (c) 2026 V2 Software LLC. All rights reserved.

#!/usr/bin/env node

/**
 * Simple CLI for testing the marketing agent.
 *
 * Usage:
 *   npx tsx src/cli.ts generate --product "..." --audience "..." --pageType landing
 *   npx tsx src/cli.ts review --file copy.txt --product "..." --audience "..."
 *   echo "some copy" | npx tsx src/cli.ts review --product "..." --audience "..."
 */

import { MarketingAgent } from './agent';
import type { CopyContext } from './agent';
import * as fs from 'node:fs';

// ---------------------------------------------------------------------------
// Argument parsing (minimal, no external deps)
// ---------------------------------------------------------------------------

function getArg(name: string, fallback?: string): string {
  const idx = process.argv.indexOf(`--${name}`);
  if (idx !== -1 && idx + 1 < process.argv.length) {
    return process.argv[idx + 1];
  }
  const envKey = `MARKETING_${name.toUpperCase()}`;
  if (process.env[envKey]) {
    return process.env[envKey]!;
  }
  if (fallback !== undefined) {
    return fallback;
  }
  console.error(`Missing required argument: --${name} (or env ${envKey})`);
  process.exit(1);
}

function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    if (process.stdin.isTTY) {
      resolve('');
      return;
    }
    const chunks: Buffer[] = [];
    process.stdin.on('data', (chunk: Buffer) => chunks.push(chunk));
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')));
    process.stdin.on('error', reject);
  });
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

async function generate(): Promise<void> {
  const context: CopyContext = {
    product: getArg('product'),
    audience: getArg('audience'),
    tone: getArg('tone', 'professional'),
    pageType: getArg('pageType', 'landing') as CopyContext['pageType'],
  };

  const model = getArg('model', 'claude-sonnet-4-20250514');
  const agent = new MarketingAgent({ model });

  console.log('Generating copy...\n');
  const result = await agent.generateCopy(context);

  console.log('--- Generated Copy ---');
  console.log(`Headline:    ${result.headline}`);
  console.log(`Subheadline: ${result.subheadline}`);
  console.log(`CTA:         ${result.cta}`);
  console.log(`Framework:   ${result.metadata.framework}`);
  console.log(`Readability: ${result.metadata.readabilityScore}`);
  console.log(`\nBody:\n${result.body}`);
}

async function review(): Promise<void> {
  const filePath = getArg('file', '');
  let copy: string;

  if (filePath) {
    if (!fs.existsSync(filePath)) {
      console.error(`File not found: ${filePath}`);
      process.exit(1);
    }
    copy = fs.readFileSync(filePath, 'utf-8');
  } else {
    copy = await readStdin();
    if (!copy.trim()) {
      console.error(
        'No copy provided. Pass --file <path> or pipe text via stdin.',
      );
      process.exit(1);
    }
  }

  const context: CopyContext = {
    product: getArg('product'),
    audience: getArg('audience'),
    tone: getArg('tone', 'professional'),
    pageType: getArg('pageType', 'landing') as CopyContext['pageType'],
  };

  const model = getArg('model', 'claude-sonnet-4-20250514');
  const agent = new MarketingAgent({ model });

  console.log('Reviewing copy...\n');
  const result = await agent.reviewCopy(copy, context);

  console.log('--- Copy Review ---');
  console.log(`Overall Score: ${result.score}/100\n`);

  if (result.issues.length > 0) {
    console.log('Issues:');
    for (const issue of result.issues) {
      console.log(
        `  [${issue.severity.toUpperCase()}] ${issue.type}: ${issue.description}`,
      );
      console.log(`    Location: "${issue.location}"`);
    }
    console.log();
  }

  if (result.suggestions.length > 0) {
    console.log('Suggestions:');
    for (const s of result.suggestions) {
      console.log(`  - ${s}`);
    }
    console.log();
  }

  console.log('Suggested Rewrite:');
  console.log(result.rewrite);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

const command = process.argv[2];

switch (command) {
  case 'generate':
    generate().catch((err) => {
      console.error('Error:', err instanceof Error ? err.message : err);
      process.exit(1);
    });
    break;
  case 'review':
    review().catch((err) => {
      console.error('Error:', err instanceof Error ? err.message : err);
      process.exit(1);
    });
    break;
  default:
    console.log(`
@jobhunter/marketing-agent CLI

Usage:
  tsx src/cli.ts generate --product "..." --audience "..." [--pageType landing] [--tone professional]
  tsx src/cli.ts review --file copy.txt --product "..." --audience "..."
  echo "copy text" | tsx src/cli.ts review --product "..." --audience "..."

Commands:
  generate   Generate new marketing copy
  review     Review and score existing copy

Options:
  --product    Product description (required)
  --audience   Target audience (required)
  --pageType   landing | pricing | feature | email (default: landing)
  --tone       Tone of voice (default: professional)
  --model      Anthropic model ID (default: claude-sonnet-4-20250514)
  --file       Path to file containing copy to review (review command)
`);
    process.exit(command ? 1 : 0);
}
