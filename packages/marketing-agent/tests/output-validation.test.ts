import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MarketingAgent } from '../src/agent';
import { HubSpotIntegration } from '../src/integrations/hubspot';

test('malformed model output is rejected without disclosing the raw response', async () => {
  const originalFetch = globalThis.fetch;
  const originalKey = process.env.ANTHROPIC_API_KEY;
  process.env.ANTHROPIC_API_KEY = 'offline-test-key';
  let reply = '{"private":"applicant@example.com"}';
  globalThis.fetch = async () => new Response(JSON.stringify({
    id: 'msg_offline', type: 'message', role: 'assistant', model: 'claude-sonnet-5-5',
    content: [{ type: 'text', text: reply }], stop_reason: 'end_turn',
    usage: { input_tokens: 1, output_tokens: 1 },
  }), { headers: { 'content-type': 'application/json' } });
  try {
    const agent = new MarketingAgent();
    const context = { product: 'Test', audience: 'Test', tone: 'clear', pageType: 'landing' as const };
    for (const text of [reply, 'applicant@example.com is not JSON', '{"score":999,"issues":[],"suggestions":[],"rewrite":"ok"}']) {
      reply = text;
      await assert.rejects(agent.reviewCopy('Copy', context), error => {
        assert(error instanceof Error);
        assert(!error.message.includes('applicant@example.com'));
        return true;
      });
    }
    reply = '["Only one"]';
    await assert.rejects(agent.generateVariants('Copy', 2));
    reply = '```json\n{"score":90,"issues":[],"suggestions":[],"rewrite":"Good"}\n```';
    assert.equal((await agent.reviewCopy('Copy', context)).score, 90);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalKey === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = originalKey;
  }
});

test('invalid variant counts are rejected before a provider request', async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new Error('Unexpected network call'); };
  try {
    for (const count of [0, -1, 1.5, NaN, Infinity, 11]) {
      await assert.rejects(new MarketingAgent().generateVariants('Copy', count), /count/i);
    }
    assert.equal(calls, 0);
  } finally { globalThis.fetch = originalFetch; }
});

test('landing page copy is text, never executable model-generated markup', () => {
  const integration = new HubSpotIntegration('offline-test-key');
  // Test the HTML boundary without sending or publishing anything to HubSpot.
  const html = (integration as unknown as {
    buildLandingPageHTML(copy: { headline: string; body: string }): string;
  }).buildLandingPageHTML({ headline: 'Title', body: '<script>alert(1)</script>\nNext line' });
  assert(!html.includes('<script>'));
  assert(html.includes('&lt;script&gt;'));
  assert(html.includes('<br>'));
});
