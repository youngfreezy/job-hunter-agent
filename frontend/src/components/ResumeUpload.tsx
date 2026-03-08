"use client";

import { useState, useEffect } from "react";
import { parseResume } from "@/lib/api";

const STORAGE_KEY = "jh_resume_text";
const FILENAME_KEY = "jh_resume_filename";

interface ResumeUploadProps {
  onResumeReady?: (text: string) => void;
}

export function ResumeUpload({ onResumeReady }: ResumeUploadProps) {
  const [resumeText, setResumeText] = useState("");
  const [fileName, setFileName] = useState("");
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY) || "";
    const savedName = localStorage.getItem(FILENAME_KEY) || "";
    setResumeText(saved);
    setFileName(savedName);
  }, []);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setFileName(file.name);

    if (file.type === "text/plain" || file.name.endsWith(".txt")) {
      const text = await file.text();
      setResumeText(text);
      localStorage.setItem(STORAGE_KEY, text);
      localStorage.setItem(FILENAME_KEY, file.name);
      onResumeReady?.(text);
      return;
    }

    setParsing(true);
    try {
      const result = await parseResume(file);
      setResumeText(result.text);
      localStorage.setItem(STORAGE_KEY, result.text);
      localStorage.setItem(FILENAME_KEY, file.name);
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
