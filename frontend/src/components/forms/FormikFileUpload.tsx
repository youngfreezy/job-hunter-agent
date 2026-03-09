// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useRef, useState } from "react";
import { useFormikContext } from "formik";
import type { SessionFormValues } from "@/lib/schemas/session";
import { parseResume } from "@/lib/api";

const STORAGE_KEY = "jh_resume_text";
const FILENAME_KEY = "jh_resume_filename";
const FILE_BYTES_KEY = "jh_resume_bytes";
const FILE_SAVED_AT_KEY = "jh_resume_saved_at";
const TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function saveResumeToStorage(text: string, fileName: string, fileBytes?: string) {
  try {
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

export function FormikFileUpload() {
  const { values, setFieldValue } = useFormikContext<SessionFormValues>();
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const restoredRef = useRef(false);

  // Restore resume from localStorage on mount if form is empty
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    if (values.resumeText) return;

    try {
      const savedText = localStorage.getItem(STORAGE_KEY) || "";
      const savedName = localStorage.getItem(FILENAME_KEY) || "";
      if (savedText) {
        setFieldValue("resumeText", savedText);
        setFieldValue("resumeFileName", savedName);
      }

      // If we have cached file bytes, re-upload to get a fresh server path
      const cached = getCachedResumeBytes();
      if (cached && savedText) {
        const file = base64ToFile(cached.bytes, cached.fileName);
        setParsing(true);
        parseResume(file)
          .then((result) => {
            if (result.file_path) {
              setFieldValue("resumeFilePath", result.file_path);
            }
          })
          .catch(() => {
            // Re-upload failed silently — text is still available, just no file for ATS upload
          })
          .finally(() => setParsing(false));
      }
    } catch {
      // ignore
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const detectedSections = SECTION_PATTERNS.filter((section) =>
    section.pattern.test(values.resumeText || "")
  ).map((section) => section.label);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setFieldValue("resumeFileName", file.name);

    // Plain text files can be read directly
    if (file.type === "text/plain" || file.name.endsWith(".txt")) {
      const text = await file.text();
      setFieldValue("resumeText", text);
      saveResumeToStorage(text, file.name);
      return;
    }

    // PDF and DOCX files: send to backend for parsing + cache bytes
    setParsing(true);
    try {
      const [result, base64] = await Promise.all([parseResume(file), fileToBase64(file)]);
      setFieldValue("resumeText", result.text);
      if (result.file_path) {
        setFieldValue("resumeFilePath", result.file_path);
      }
      saveResumeToStorage(result.text, file.name, base64);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to parse file";
      setError(msg);
      setFieldValue("resumeFileName", "");
      setFieldValue("resumeText", "");
      e.target.value = "";
    } finally {
      setParsing(false);
    }
  };

  return (
    <div>
      <div className="rounded-2xl border-2 border-dashed border-zinc-300 p-6 dark:border-zinc-700">
        <input
          type="file"
          accept=".txt,.pdf,.docx"
          onChange={handleFileUpload}
          className="hidden"
          id="resume-upload"
          disabled={parsing}
        />
        <label
          htmlFor="resume-upload"
          className={`block cursor-pointer text-center ${
            parsing ? "pointer-events-none opacity-60" : ""
          }`}
        >
          <div className="text-sm text-zinc-600 dark:text-zinc-400">
            {parsing ? (
              <span className="text-blue-600 font-medium">Extracting text from your resume...</span>
            ) : values.resumeFileName ? (
              <span className="text-green-600 font-medium">{values.resumeFileName}</span>
            ) : (
              <>
                <span className="font-medium text-zinc-900 dark:text-white">Click to upload</span>{" "}
                your resume
              </>
            )}
          </div>
          <p className="text-xs text-zinc-500 mt-1">.txt, .pdf, or .docx</p>
        </label>

        {values.resumeFileName && !parsing && (
          <div className="mt-4 space-y-3 rounded-xl bg-zinc-50 p-4 text-left dark:bg-zinc-900/60">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
                  Parsed Resume
                </p>
                <p className="mt-1 text-sm font-medium text-zinc-900 dark:text-white">
                  {values.resumeFileName}
                </p>
              </div>
              <label
                htmlFor="resume-upload"
                className="cursor-pointer text-xs font-medium text-blue-600 hover:text-blue-700"
              >
                Replace file
              </label>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
                <p className="text-xs text-zinc-500">Extracted length</p>
                <p className="mt-1 text-lg font-semibold">
                  {values.resumeText.length.toLocaleString()} characters
                </p>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-950">
                <p className="text-xs text-zinc-500">Detected sections</p>
                <p className="mt-1 text-sm font-medium">
                  {detectedSections.length > 0
                    ? detectedSections.join(", ")
                    : "No standard headings detected yet"}
                </p>
              </div>
            </div>

            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
                Parsed text preview
              </p>
              <div className="mt-2 max-h-40 overflow-y-auto rounded-xl border border-zinc-200 bg-white p-3 text-sm text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300">
                {values.resumeText.slice(0, 1200)}
                {values.resumeText.length > 1200 ? "..." : ""}
              </div>
            </div>
          </div>
        )}
      </div>
      {error && <p className="text-xs text-red-600 mt-1.5">{error}</p>}
    </div>
  );
}
