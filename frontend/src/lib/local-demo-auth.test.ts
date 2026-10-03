import { describe, expect, it } from 'vitest';
import { demoAuthEnabled, validDemoCredentials } from './local-demo-auth';
const env = { NODE_ENV: 'development', ENABLE_CREDENTIALS_AUTH: 'true', LOCAL_DEMO_EMAIL: 'demo@example.test', LOCAL_DEMO_PASSWORD: 'long-demo-password' };
describe('local demo sign in', () => {
 it('requires opt in and rejects production', () => {
  expect(demoAuthEnabled(env)).toBe(true);
  expect(demoAuthEnabled({ ...env, NODE_ENV: 'production' })).toBe(false);
  expect(demoAuthEnabled({ ...env, ENABLE_CREDENTIALS_AUTH: 'false' })).toBe(false);
 });
 it('requires the configured email and password', () => {
  expect(validDemoCredentials('demo@example.test', 'long-demo-password', env)).toBe(true);
  expect(validDemoCredentials('other@example.test', 'long-demo-password', env)).toBe(false);
  expect(validDemoCredentials('demo@example.test', 'wrong', env)).toBe(false);
 });
});
