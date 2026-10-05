import { beforeEach, describe, expect, it, vi } from "vitest";
import { getCachedResumeFile, readSavedResume, saveResumeToStorage, saveResumeUuid, clearResumeUuid } from "./resume-storage";

const storage = new Map<string, string>();
const now = Date.UTC(2026, 9, 5);
beforeEach(() => {
  storage.clear();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  });
});

describe("resume cache boundary", () => {
  it("restores the current attachment with its filename and media type", async () => {
    saveResumeToStorage("Current resume", "current.pdf", btoa("current-pdf"), now);
    const file = getCachedResumeFile(now);
    expect(readSavedResume()).toEqual({ text: "Current resume", fileName: "current.pdf" });
    expect(file?.name).toBe("current.pdf");
    expect(file?.type).toBe("application/pdf");
    expect(await file?.text()).toBe("current-pdf");
  });

  it("replacing a resume invalidates the previous server identity and bytes", () => {
    saveResumeToStorage("Original", "original.pdf", btoa("old"), now);
    saveResumeUuid("old-uuid");
    saveResumeToStorage("Replacement", "replacement.txt");
    expect(getCachedResumeFile(now)).toBeNull();
    expect(storage.get("jh_resume_uuid")).toBeUndefined();
    expect(readSavedResume().fileName).toBe("replacement.txt");
  });

  it.each(["garbage", "NaN", String(now + 1), String(now - 8 * 24 * 60 * 60 * 1000)])(
    "rejects expired or invalid attachment timestamp %s", (timestamp) => {
      saveResumeToStorage("Resume", "resume.txt", btoa("content"), now);
      storage.set("jh_resume_saved_at", timestamp);
      expect(getCachedResumeFile(now)).toBeNull();
      expect(storage.get("jh_resume_bytes")).toBeUndefined();
    },
  );

  it("does not crash the upload screen when cached base64 is corrupt", () => {
    saveResumeToStorage("Resume", "resume.pdf", "%%% corrupt %%%", now);
    expect(getCachedResumeFile(now)).toBeNull();
    expect(storage.get("jh_resume_bytes")).toBeUndefined();
  });

  it("remains usable when browser storage is disabled", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => { throw new Error("Storage blocked"); },
      setItem: () => { throw new Error("Storage blocked"); },
      removeItem: () => { throw new Error("Storage blocked"); },
    });
    expect(readSavedResume()).toEqual({ text: "", fileName: "" });
    expect(getCachedResumeFile(now)).toBeNull();
    expect(() => saveResumeToStorage("Resume", "resume.txt", "", now)).not.toThrow();
    expect(() => saveResumeUuid("uuid")).not.toThrow();
    expect(() => clearResumeUuid()).not.toThrow();
  });

  it("keeps text usable when attachment bytes exceed browser storage quota", () => {
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        if (key === "jh_resume_bytes") throw new Error("Quota exceeded");
        storage.set(key, value);
      },
      removeItem: (key: string) => storage.delete(key),
    });
    saveResumeToStorage("Resume", "resume.txt", btoa("content"), now);
    expect(readSavedResume()).toEqual({ text: "Resume", fileName: "resume.txt" });
    expect(getCachedResumeFile(now)).toBeNull();
  });
});
