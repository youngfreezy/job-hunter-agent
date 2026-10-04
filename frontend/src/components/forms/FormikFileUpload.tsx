// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useRef, useState } from "react";
import { useFormikContext } from "formik";
import type { SessionFormValues } from "@/lib/schemas/session";
import { parseResume } from "@/lib/api";
import { FilePicker } from "./FilePicker";

type ParseFn = (file: File) => Promise<{ text: string; filename: string; file_path?: string; resume_uuid?: string }>;

const STORAGE_KEY = "jh_resume_text";
const FILENAME_KEY = "jh_resume_filename";
const FILE_BYTES_KEY = "jh_resume_bytes";
const FILE_SAVED_AT_KEY = "jh_resume_saved_at";
const TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function saveResumeToStorage(text: string, fileName: string, fileBytes?: string) {
  try {
    localStorage.removeItem("jh_resume_uuid");
    localStorage.removeItem(FILE_BYTES_KEY);
    localStorage.removeItem(FILE_SAVED_AT_KEY);
    localStorage.setItem(STORAGE_KEY, text);
    localStorage.setItem(FILENAME_KEY, fileName);
    if (fileBytes) {
      localStorage.setItem(FILE_BYTES_KEY, fileBytes);
      localStorage.setItem(FILE_SAVED_AT_KEY, Date.now().toString());
    }
  } catch {
    // localStorage full — try without bytes
    try {
      localStorage.removeItem(FILE_BYTES_KEY);
      localStorage.removeItem(FILE_SAVED_AT_KEY);
      localStorage.setItem(STORAGE_KEY, text);
      localStorage.setItem(FILENAME_KEY, fileName);
    } catch {
      // truly full, give up
    }
  }
}

function getCachedResumeBytes(): { bytes: string; fileName: string } | null {
  try {
    const bytes = localStorage.getItem(FILE_BYTES_KEY);
    const savedAt = localStorage.getItem(FILE_SAVED_AT_KEY);
    const fileName = localStorage.getItem(FILENAME_KEY) || "resume.pdf";
    if (!bytes || !savedAt) return null;
    if (Date.now() - parseInt(savedAt, 10) > TTL_MS) {
      // Expired — clean up
      localStorage.removeItem(FILE_BYTES_KEY);
      localStorage.removeItem(FILE_SAVED_AT_KEY);
      return null;
    }
    return { bytes, fileName };
  } catch {
    return null;
  }
}

function base64ToFile(base64: string, fileName: string): File {
  const byteString = atob(base64);
  const bytes = new Uint8Array(byteString.length);
  for (let i = 0; i < byteString.length; i++) {
    bytes[i] = byteString.charCodeAt(i);
  }
  const ext = fileName.split(".").pop()?.toLowerCase() || "pdf";
  const mime =
    ext === "pdf"
      ? "application/pdf"
      : ext === "docx"
      ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
      : "text/plain";
  return new File([bytes], fileName, { type: mime });
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Strip the data:... prefix to get raw base64
      const base64 = result.split(",")[1] || result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const SECTION_PATTERNS = [
  { label: "Summary", pattern: /\b(summary|profile|about)\b/i },
  { label: "Experience", pattern: /\b(experience|employment|work history)\b/i },
  { label: "Skills", pattern: /\b(skills|technical skills|core competencies)\b/i },
  { label: "Education", pattern: /\b(education|academic)\b/i },
  { label: "Projects", pattern: /\b(projects|selected work|portfolio)\b/i },
];

export function FormikFileUpload({ parseFn }: { parseFn?: ParseFn } = {}) {
  const parse = parseFn || parseResume;
  const { values, errors, setFieldValue } = useFormikContext<SessionFormValues>();
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const restoredRef = useRef(false);

  // Restore resume from localStorage on mount if form is empty,
  // and ALWAYS re-upload cached bytes to get a fresh server-side UUID.
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;

    // Restore text from localStorage if form is empty
    if (!values.resumeText) {
      try {
        const savedText = localStorage.getItem(STORAGE_KEY) || "";
        const savedName = localStorage.getItem(FILENAME_KEY) || "";
        if (savedText) {
          setFieldValue("resumeText", savedText);
          setFieldValue("resumeFileName", savedName);
        }
      } catch {
        // ignore
      }
    }

    // Always re-upload cached bytes to get a fresh UUID/path.
    // Formik persistence may restore a stale resumeFileUuid from a previous session.
    setFieldValue("resumeFilePath", "");
    setFieldValue("resumeFileUuid", "");
    try { localStorage.removeItem("jh_resume_uuid"); } catch {}
    const cached = getCachedResumeBytes();
    if (cached) {
      const file = base64ToFile(cached.bytes, cached.fileName);
      setParsing(true);
      parse(file)
        .then((result) => {
          if (result.file_path) {
            setFieldValue("resumeFilePath", result.file_path);
          }
          if (result.resume_uuid) {
            setFieldValue("resumeFileUuid", result.resume_uuid);
            try { localStorage.setItem("jh_resume_uuid", result.resume_uuid); } catch {}
          }
        })
        .catch(() => {
          setError("Could not restore the saved resume file. Please upload it again.");
          setFieldValue("resumeText", "");
        })
        .finally(() => setParsing(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const detectedSections = SECTION_PATTERNS.filter((section) =>
    section.pattern.test(values.resumeText || "")
  ).map((section) => section.label);

  const handleFileUpload = async (file: File) => {
    setError(null);
    setFieldValue("resumeFileName", file.name);
    setFieldValue("resumeText", "");
    setFieldValue("resumeFilePath", "");
    setFieldValue("resumeFileUuid", "");
    saveResumeToStorage("", file.name);


    // All advertised formats need server-owned bytes/UUID for browser upload.
    setParsing(true);
    try {
      const [result, base64] = await Promise.all([parse(file), fileToBase64(file)]);
      setFieldValue("resumeText", result.text);
      saveResumeToStorage(result.text, file.name, base64);
      setFieldValue("resumeFilePath", result.file_path || "");
      setFieldValue("resumeFileUuid", result.resume_uuid || "");
      if (result.resume_uuid) {
        try { localStorage.setItem("jh_resume_uuid", result.resume_uuid); } catch {}
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to parse file";
      setError(msg);
      setFieldValue("resumeFileName", "");
      setFieldValue("resumeText", "");
    } finally {
      setParsing(false);
    }
  };

  return (
    <div>
      <FilePicker
        id="resume-upload"
        accept=".txt,.pdf,.docx"
        onFile={handleFileUpload}
        disabled={parsing}
        buttonLabel={values.resumeFileName ? "Replace file" : "Choose resume"}
        status={parsing ? "Reading your resume…" : error ?? undefined}
      >
        {values.resumeFileName ? (
          <span className="font-medium text-foreground">{values.resumeFileName}</span>
        ) : (
          <span>PDF, DOCX or TXT</span>
        )}
      </FilePicker>
      {values.resumeFileName && !parsing && typeof errors.resumeText === "string" && (
        <p role="alert" className="mt-2 text-sm text-destructive">{errors.resumeText}</p>
      )}
      {values.resumeFileName && !parsing && (
        <div className="mt-3 space-y-3">
          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-muted-foreground">Extracted</dt>
            <dd className="font-mono tabular-nums">
              {values.resumeText.length.toLocaleString()} characters
            </dd>
            <dt className="text-muted-foreground">Sections found</dt>
            <dd>
              {detectedSections.length > 0
                ? detectedSections.join(", ")
                : "No standard headings found"}
            </dd>
          </dl>
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
              Preview parsed text
            </summary>
            <div className="mt-2 max-h-40 overflow-y-auto rounded-md border border-border bg-background p-3 text-foreground">
              {values.resumeText.slice(0, 1200)}
              {values.resumeText.length > 1200 ? "…" : ""}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}
