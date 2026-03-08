"use client";

import { useEffect, useRef, useState } from "react";
import { useFormikContext } from "formik";
import type { SessionFormValues } from "@/lib/schemas/session";
import { parseResume } from "@/lib/api";

const STORAGE_KEY = "jh_resume_text";
const FILENAME_KEY = "jh_resume_filename";

function saveResumeToStorage(text: string, fileName: string) {
  try {
    localStorage.setItem(STORAGE_KEY, text);
    localStorage.setItem(FILENAME_KEY, fileName);
  } catch {
    // localStorage full or unavailable
  }
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

    // PDF and DOCX files: send to backend for parsing
    setParsing(true);
    try {
      const result = await parseResume(file);
      setFieldValue("resumeText", result.text);
      if (result.file_path) {
        setFieldValue("resumeFilePath", result.file_path);
      }
      saveResumeToStorage(result.text, file.name);
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
              <span className="text-blue-600 font-medium">
                Extracting text from your resume...
              </span>
            ) : values.resumeFileName ? (
              <span className="text-green-600 font-medium">
                {values.resumeFileName}
              </span>
            ) : (
              <>
                <span className="font-medium text-zinc-900 dark:text-white">
                  Click to upload
                </span>{" "}
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
