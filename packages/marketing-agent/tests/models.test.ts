import assert from 'node:assert/strict';
import { test } from 'node:test';
import { MarketingAgent } from '../src/agent';

test('all marketing operations send the latest Sonnet with supported sampling and no forced tools', async () => {
  const originalFetch = globalThis.fetch;
  const originalKey = process.env.ANTHROPIC_API_KEY;
  process.env.ANTHROPIC_API_KEY = 'offline-test-key';
  const requests: Record<string, unknown>[] = [];
  const replies = [
    { headline: 'Test', subheadline: 'Test', body: 'Copy', cta: 'Go', metadata: { framework: 'AIDA', readabilityScore: 80 } },
    { score: 90, issues: [], suggestions: [], rewrite: 'Revised' },
    ['One', 'Two'],
    { score: 80, issues: [], suggestions: [], rewrite: 'Custom model' },
  ];
  globalThis.fetch = async (_input, init) => {
    requests.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({ id: 'msg_offline', type: 'message', role: 'assistant', model: 'claude-sonnet-5-5', content: [{ type: 'thinking', thinking: 'Offline reasoning fixture', signature: 'offline-signature' }, { type: 'text', text: JSON.stringify(replies.shift()) }], stop_reason: 'end_turn', stop_sequence: null, usage: { input_tokens: 1, output_tokens: 1 } }), { headers: { 'content-type': 'application/json' } });
  };
  try {
    const agent = new MarketingAgent();
    const context = { product: 'Test', audience: 'Test', tone: 'professional', pageType: 'landing' as const };
    assert.equal((await agent.generateCopy(context)).headline, 'Test');
    assert.equal((await agent.reviewCopy('Copy', context)).score, 90);
    assert.deepEqual(await agent.generateVariants('Copy', 2), ['One', 'Two']);
    assert.equal(requests.length, 3);
    assert.deepEqual(requests.map(request => request.max_tokens), [4096, 4096, 8192]);
    for (const request of requests) {
      assert.equal(request.model, 'claude-sonnet-5-5');
      assert.equal(request.temperature, undefined, 'Claude 5.5 uses provider defaults, never temperature 0');
      assert.equal(request.tool_choice, undefined);
      assert.equal(request.tools, undefined);
      assert.equal(request.output_format, undefined);
      assert.ok(Array.isArray(request.system) && request.system.length > 0, 'System instructions must survive SDK option renames');
      assert.equal(request.top_p, undefined);
      assert.equal(request.top_k, undefined);
    }
    await new MarketingAgent({ model: 'claude-haiku-4-5-20251001', maxTokens: 512 }).reviewCopy('Copy', context);
    assert.equal(requests[3].model, 'claude-haiku-4-5-20251001');
    assert.equal(requests[3].temperature, 0, 'Preserve legacy model override sampling');
    assert.equal(requests[3].max_tokens, 512, 'Preserve the public maxTokens option across the SDK rename');
  } finally {
    globalThis.fetch = originalFetch;
    if (originalKey === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = originalKey;
  }
});
