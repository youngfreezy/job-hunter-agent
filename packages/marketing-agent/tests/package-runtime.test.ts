import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

test('built ESM package and CLI load without a TypeScript loader or provider credentials', () => {
  const loaded = spawnSync(process.execPath, ['--input-type=module', '-e', `
    const api = await import('./dist/index.js');
    if (typeof api.MarketingAgent !== 'function') throw new Error('Missing public agent');
    for (const tool of [api.copyGeneratorTool, api.copyReviewerTool]) {
      if (!tool.inputSchema || typeof tool.execute !== 'function') throw new Error('Invalid SDK tool');
    }
  `], { encoding: 'utf8' });
  assert.equal(loaded.status, 0, loaded.stderr);
  const cli = spawnSync(process.execPath, ['dist/cli.js'], { encoding: 'utf8' });
  assert.equal(cli.status, 0, cli.stderr);
  assert.match(cli.stdout, /generate.*Generate new marketing copy/);
});
