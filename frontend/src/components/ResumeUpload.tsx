// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState, useEffect, useRef } from "react";
import { parseResume } from "@/lib/api";

const STORAGE_KEY = "jh_resume_text";
const FILENAME_KEY = "jh_resume_filename";
const FILE_BYTES_KEY = "jh_resume_bytes";
const FILE_SAVED_AT_KEY = "jh_resume_saved_at";
const TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.split(",")[1] || result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function saveResumeToStorage(text: string, fileName: string, fileBytes?: string) {
  try {
    localStorage.setItem(STORAGE_KEY, text);
    localStorage.setItem(FILENAME_KEY, fileName);
    if (fileBytes) {
      localStorage.setItem(FILE_BYTES_KEY, fileBytes);
      localStorage.setItem(FILE_SAVED_AT_KEY, Date.now().toString());
    }
  } catch {
    try {
      localStorage.removeItem(FILE_BYTES_KEY);
      localStorage.removeItem(FILE_SAVED_AT_KEY);
      localStorage.setItem(STORAGE_KEY, text);
      localStorage.setItem(FILENAME_KEY, fileName);
    } catch {
      // truly full
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
  const mime = ext === "pdf" ? "application/pdf"
    : ext === "docx" ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    : "text/plain";
  return new File([bytes], fileName, { type: mime });
}

interface ResumeUploadProps {
  onResumeReady?: (text: string) => void;
}

export function ResumeUpload({ onResumeReady }: ResumeUploadProps) {
  const [resumeText, setResumeText] = useState("");
  const [fileName, setFileName] = useState("");
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const restoredRef = useRef(false);

  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;

    const saved = localStorage.getItem(STORAGE_KEY) || "";
    const savedName = localStorage.getItem(FILENAME_KEY) || "";
    setResumeText(saved);
    setFileName(savedName);

    // If we have cached file bytes, re-upload to get a fresh server path
    const cached = getCachedResumeBytes();
    if (cached && saved) {
      const file = base64ToFile(cached.bytes, cached.fileName);
      setParsing(true);
      parseResume(file)
        .catch(() => {})
        .finally(() => setParsing(false));
    }
  }, []);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setFileName(file.name);

    if (file.type === "text/plain" || file.name.endsWith(".txt")) {
      const text = await file.text();
      setResumeText(text);
      saveResumeToStorage(text, file.name);
      onResumeReady?.(text);
      return;
    }

    setParsing(true);
    try {
      const [result, base64] = await Promise.all([
        parseResume(file),
        fileToBase64(file),
      ]);
      setResumeText(result.text);
      saveResumeToStorage(result.text, file.name, base64);
      onResumeReady?.(result.text);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to parse file";
      setError(msg);
      setFileName("");
    } finally {
      setParsing(false);
    }
  }

  const hasResume = resumeText.length > 0;

  return (
    <div className="space-y-2">
      <input
        type="file"
        accept=".txt,.pdf,.docx"
        onChange={handleFile}
        className="hidden"
        id="resume-upload-standalone"
        disabled={parsing}
      />

      {hasResume ? (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 dark:border-emerald-800 dark:bg-emerald-950/30">
          <svg className="h-5 w-5 text-emerald-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-emerald-800 dark:text-emerald-200">
              Resume loaded{fileName ? `: ${fileName}` : ""}
            </p>
            <p className="text-xs text-emerald-600 dark:text-emerald-400">
              {resumeText.length.toLocaleString()} characters
            </p>
          </div>
          <label
            htmlFor="resume-upload-standalone"
            className="cursor-pointer text-xs font-medium text-emerald-700 hover:text-emerald-900 dark:text-emerald-300 dark:hover:text-emerald-100"
          >
            Replace
          </label>
        </div>
      ) : (
        <label
          htmlFor="resume-upload-standalone"
          className={`block cursor-pointer rounded-lg border-2 border-dashed border-zinc-300 px-4 py-4 text-center transition-colors hover:border-zinc-400 dark:border-zinc-700 dark:hover:border-zinc-500 ${
            parsing ? "pointer-events-none opacity-60" : ""
          }`}
        >
          {parsing ? (
            <p className="text-sm text-blue-600 font-medium">Extracting text...</p>
          ) : (
            <>
              <p className="text-sm">
                <span className="font-medium text-zinc-900 dark:text-white">Upload your resume</span>
                {" "}to get started
              </p>
              <p className="text-xs text-muted-foreground mt-1">.txt, .pdf, or .docx</p>
            </>
          )}
        </label>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
