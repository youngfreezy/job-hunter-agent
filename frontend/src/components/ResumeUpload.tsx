// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState, useEffect, useRef } from "react";
import { parseResume } from "@/lib/api";
import { FilePicker } from "@/components/forms/FilePicker";
import { clearResumeUuid, fileToBase64, getCachedResumeFile, readSavedResume, saveResumeToStorage, saveResumeUuid } from "@/lib/resume-storage";

export interface ResumeAttachment {
  fileName: string;
  resumeUuid: string;
  filePath: string;
}

interface ResumeUploadProps {
  onResumeReady?: (text: string, attachment: ResumeAttachment | null) => void;
}

export function ResumeUpload({ onResumeReady }: ResumeUploadProps) {
  const [resumeText, setResumeText] = useState("");
  const [fileName, setFileName] = useState("");
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const restoredRef = useRef(false);
  const onResumeReadyRef = useRef(onResumeReady);
  onResumeReadyRef.current = onResumeReady;

  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;

    const { text: saved, fileName: savedName } = readSavedResume();
    setResumeText(saved);
    setFileName(savedName);

    // If we have cached file bytes, re-upload to get a fresh server path
    clearResumeUuid();
    const file = getCachedResumeFile();
    if (file && saved) {
      setParsing(true);
      parseResume(file)
        .then((result) => {
          setResumeText(result.text);
          if (result.resume_uuid) saveResumeUuid(result.resume_uuid);
          onResumeReadyRef.current?.(result.text, {
            fileName: file.name, resumeUuid: result.resume_uuid || "", filePath: result.file_path || "",
          });
        })
        .catch(() => {
          setError("Could not restore the saved resume file. Please upload it again.");
          setResumeText("");
          onResumeReadyRef.current?.("", null);
        })
        .finally(() => setParsing(false));
    } else if (saved) {
      setError("Saved resume attachment is unavailable. Please upload it again.");
      onResumeReadyRef.current?.(saved, null);
    }
  }, []);

  async function handleFile(file: File) {
    setError(null);
    setFileName(file.name);
    setResumeText("");
    saveResumeToStorage("", file.name);
    onResumeReady?.("", null);

    setParsing(true);
    try {
      const [result, base64] = await Promise.all([parseResume(file), fileToBase64(file)]);
      setResumeText(result.text);
      saveResumeToStorage(result.text, file.name, base64);
      if (result.resume_uuid) {
        saveResumeUuid(result.resume_uuid);
      }
      onResumeReady?.(result.text, {
        fileName: file.name, resumeUuid: result.resume_uuid || "", filePath: result.file_path || "",
      });
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
