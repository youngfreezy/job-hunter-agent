import { describe, expect, it } from "vitest";
import { restoreSessionDraft } from "./session-draft";
import { sessionInitialValues } from "./schemas/session";

describe("session draft restoration", () => {
  it.each([null, [], "draft", 7])("uses defaults for a non-object draft %j", (draft) => {
    expect(restoreSessionDraft(draft)).toEqual(sessionInitialValues);
  });
  it("restores incomplete editing state without mutating the draft or defaults", () => {
    const draft = Object.freeze({ keywords: "AI", salaryMin: "2", resumeText: "Draft without an email yet", maxJobs: 25 });
    expect(restoreSessionDraft(draft)).toMatchObject({ keywords: "AI", salaryMin: "2", resumeText: draft.resumeText, maxJobs: 20 });
    expect(draft.maxJobs).toBe(25);
    expect(sessionInitialValues.keywords).toBe("");
  });
  it("discards untrusted types, unknown fields, and expired attachment references", () => {
    const restored = restoreSessionDraft({ keywords: ["AI"], remoteOnly: "false", jobBoards: ["indeed", null], resumeFileUuid: "old", resumeFilePath: "/old/resume.pdf", extra: "ignore" });
    expect(restored).toEqual(sessionInitialValues);
  });
  it("validates enum fields and clamps counts to integer job limits", () => {
    expect(restoreSessionDraft({ maxJobs: 3.9, minimumSubmittedApplications: 9, tailoringQuality: "custom", applicationMode: "invalid", searchRadius: 3 })).toMatchObject({
      maxJobs: 3, minimumSubmittedApplications: 3, tailoringQuality: "standard", applicationMode: "auto_apply", searchRadius: 100,
    });
  });
  it("retains explicit false flags and valid user settings", () => {
    expect(restoreSessionDraft({ remoteOnly: true, generateCoverLetters: false, jobBoards: ["indeed"], applicationMode: "materials_only", tailoringQuality: "premium" })).toMatchObject({
      remoteOnly: true, generateCoverLetters: false, jobBoards: ["indeed"], applicationMode: "materials_only", tailoringQuality: "premium",
    });
  });
});
