/** Browser persistence is optional; current upload state remains the source of truth. */
const KEYS = {
  text: "jh_resume_text",
  fileName: "jh_resume_filename",
  bytes: "jh_resume_bytes",
  savedAt: "jh_resume_saved_at",
  uuid: "jh_resume_uuid",
} as const;
const TTL_MS = 7 * 24 * 60 * 60 * 1000;

export function readSavedResume(): { text: string; fileName: string } {
  try {
    return { text: localStorage.getItem(KEYS.text) || "", fileName: localStorage.getItem(KEYS.fileName) || "" };
  } catch {
    return { text: "", fileName: "" };
  }
}

export function clearResumeUuid(): void {
  try { localStorage.removeItem(KEYS.uuid); } catch { /* Storage is optional. */ }
}

export function saveResumeUuid(uuid: string): void {
  try { localStorage.setItem(KEYS.uuid, uuid); } catch { /* Storage is optional. */ }
}

function clearCachedAttachment(): void {
  try {
    localStorage.removeItem(KEYS.bytes);
    localStorage.removeItem(KEYS.savedAt);
  } catch { /* Storage is optional. */ }
}

export function saveResumeToStorage(text: string, fileName: string, fileBytes?: string, now = Date.now()): void {
  clearResumeUuid();
  clearCachedAttachment();
  try {
    localStorage.setItem(KEYS.text, text);
    localStorage.setItem(KEYS.fileName, fileName);
    if (fileBytes) {
      localStorage.setItem(KEYS.bytes, fileBytes);
      localStorage.setItem(KEYS.savedAt, String(now));
    }
  } catch {
    // A quota failure must not leave bytes without their freshness marker.
    clearCachedAttachment();
  }
}

/** Validate storage before decoding it; malformed or expired data requires a new upload. */
export function getCachedResumeFile(now = Date.now()): File | null {
  try {
    const bytes = localStorage.getItem(KEYS.bytes);
    const savedAt = Number(localStorage.getItem(KEYS.savedAt));
    if (!bytes) return null;
    const age = now - savedAt;
    if (!Number.isFinite(savedAt) || savedAt <= 0 || age < 0 || age > TTL_MS) {
      clearCachedAttachment();
      return null;
    }
    const fileName = localStorage.getItem(KEYS.fileName) || "resume.pdf";
    const decoded = Uint8Array.from(atob(bytes), (character) => character.charCodeAt(0));
    const extension = fileName.split(".").pop()?.toLowerCase();
    const type = extension === "pdf" ? "application/pdf"
      : extension === "docx" ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      : "text/plain";
    return new File([decoded], fileName, { type });
  } catch {
    clearCachedAttachment();
    return null;
  }
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("Could not read the resume file."));
        return;
      }
      resolve(reader.result.slice(reader.result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(new Error("Could not read the resume file."));
    reader.onabort = () => reject(new Error("Reading the resume file was cancelled."));
    reader.readAsDataURL(file);
  });
}
