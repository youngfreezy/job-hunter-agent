import { afterEach, describe, expect, it, vi } from "vitest";
import { configSchema } from "./session";

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });
describe("one-job discovery demo", () => {
  it("allows one attempt with a one-submission target", async () => {
    expect(await configSchema.isValid({ maxJobs: 1, minimumSubmittedApplications: 1 })).toBe(true);
  });
  it("still rejects zero jobs and submission targets above the attempt count", async () => {
    expect(await configSchema.isValid({ maxJobs: 0 })).toBe(false);
    expect(await configSchema.isValid({ maxJobs: 1, minimumSubmittedApplications: 2 })).toBe(false);
  });
  it("defaults new demo discovery runs to one job", async () => {
    vi.stubEnv("NEXT_PUBLIC_BROWSERBASE_DEMO", "true");
    vi.resetModules();
    const { sessionInitialValues } = await import("./session");
    expect(sessionInitialValues.maxJobs).toBe(1);
  });
});
