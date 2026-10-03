import { timingSafeEqual } from "node:crypto";

type DemoEnvironment = Record<string, string | undefined>;

export function demoAuthEnabled(env: DemoEnvironment = process.env): boolean {
  return env.NODE_ENV === "development" && env.ENABLE_CREDENTIALS_AUTH === "true"
    && !!env.LOCAL_DEMO_EMAIL && (env.LOCAL_DEMO_PASSWORD?.length ?? 0) >= 16;
}

export function validDemoCredentials(email: string, password: string, env: DemoEnvironment = process.env): boolean {
  if (!demoAuthEnabled(env) || email !== env.LOCAL_DEMO_EMAIL) return false;
  const expected = Buffer.from(env.LOCAL_DEMO_PASSWORD!);
  const actual = Buffer.from(password);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}
