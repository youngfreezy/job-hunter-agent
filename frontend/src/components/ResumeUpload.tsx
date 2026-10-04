// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState, useEffect, useRef } from "react";
import { parseResume } from "@/lib/api";
import { FilePicker } from "@/components/forms/FilePicker";

const STORAGE_KEY = "jh_resume_text";
const FILENAME_KEY = "jh_resume_filename";
const FILE_BYTES_KEY = "jh_resume_bytes";
const FILE_SAVED_AT_KEY = "jh_resume_saved_at";
const RESUME_UUID_KEY = "jh_resume_uuid";
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
  const mime =
    ext === "pdf"
      ? "application/pdf"
      : ext === "docx"
      ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
        .then((result) => {
          if (result.resume_uuid) {
            try { localStorage.setItem(RESUME_UUID_KEY, result.resume_uuid); } catch {}
          }
        })
        .catch(() => {})
        .finally(() => setParsing(false));
    }
  }, []);

  async function handleFile(file: File) {
    setError(null);
    setFileName(file.name);
    setResumeText("");
    saveResumeToStorage("", file.name);
    onResumeReady?.("");

    if (file.type === "text/plain" || file.name.endsWith(".txt")) {
      const text = await file.text();
      setResumeText(text);
      saveResumeToStorage(text, file.name);
      onResumeReady?.(text);
      return;
    }

    setParsing(true);
    try {
      const [result, base64] = await Promise.all([parseResume(file), fileToBase64(file)]);
      setResumeText(result.text);
      saveResumeToStorage(result.text, file.name, base64);
      if (result.resume_uuid) {
        try { localStorage.setItem(RESUME_UUID_KEY, result.resume_uuid); } catch {}
      }
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
    <FilePicker
      id="resume-upload-standalone"
      accept=".txt,.pdf,.docx"
      onFile={handleFile}
      disabled={parsing}
      buttonLabel={hasResume ? "Replace" : "Choose resume"}
      status={parsing ? "Reading your resume…" : error ?? undefined}
    >
      {hasResume ? (
        <span>
          <span className="font-medium text-foreground">{fileName || "Resume loaded"}</span>{" "}
          <span className="font-mono tabular-nums">
            {resumeText.length.toLocaleString()} characters
          </span>
        </span>
      ) : (
        <span>PDF, DOCX or TXT</span>
      )}
    </FilePicker>
  );
}
