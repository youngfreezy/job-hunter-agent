// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useRef, useState } from "react";
import { useFormikContext } from "formik";
import type { SessionFormValues } from "@/lib/schemas/session";
import { parseResume } from "@/lib/api";
import { FilePicker } from "./FilePicker";
import { clearResumeUuid, fileToBase64, getCachedResumeFile, readSavedResume, saveResumeToStorage, saveResumeUuid } from "@/lib/resume-storage";

type ParseFn = (file: File) => Promise<{ text: string; filename: string; file_path?: string; resume_uuid?: string }>;

const SECTION_PATTERNS = [
  { label: "Summary", pattern: /\b(summary|profile|about)\b/i },
  { label: "Experience", pattern: /\b(experience|employment|work history)\b/i },
  { label: "Skills", pattern: /\b(skills|technical skills|core competencies)\b/i },
  { label: "Education", pattern: /\b(education|academic)\b/i },
  { label: "Projects", pattern: /\b(projects|selected work|portfolio)\b/i },
];

export function FormikFileUpload({ parseFn }: { parseFn?: ParseFn } = {}) {
  const parse = parseFn || parseResume;
  const { values, errors, setValues } = useFormikContext<SessionFormValues>();
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const restoredRef = useRef(false);

  // Restore resume from localStorage on mount if form is empty,
  // and ALWAYS re-upload cached bytes to get a fresh server-side UUID.
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;

    const saved = readSavedResume();
    clearResumeUuid();
    const file = getCachedResumeFile();
    // Draft text may belong to another upload. Related fields form one state transition.
    void setValues((current) => ({
      ...current,
      resumeText: file ? "" : current.resumeText || saved.text,
      resumeFileName: file?.name || current.resumeFileName || saved.fileName,
      resumeFilePath: "",
      resumeFileUuid: "",
    }), !file);
    if (file) {
      setParsing(true);
      parse(file)
        .then(async (result) => {
          await setValues((current) => ({
            ...current, resumeText: result.text, resumeFileName: file.name,
            resumeFilePath: result.file_path || "", resumeFileUuid: result.resume_uuid || "",
          }));
          if (result.resume_uuid) saveResumeUuid(result.resume_uuid);
        })
        .catch(() => {
          setError("Could not restore the saved resume file. Please upload it again.");
          void setValues((current) => ({ ...current, resumeText: "" }));
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
    void setValues((current) => ({
      ...current, resumeFileName: file.name, resumeText: "", resumeFilePath: "", resumeFileUuid: "",
    }), false);
    saveResumeToStorage("", file.name);

    // All advertised formats need server-owned bytes/UUID for browser upload.
    setParsing(true);
    try {
      const [result, base64] = await Promise.all([parse(file), fileToBase64(file)]);
      await setValues((current) => ({
        ...current, resumeText: result.text, resumeFileName: file.name,
        resumeFilePath: result.file_path || "", resumeFileUuid: result.resume_uuid || "",
      }));
      saveResumeToStorage(result.text, file.name, base64);
      if (result.resume_uuid) {
        saveResumeUuid(result.resume_uuid);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to parse file";
      setError(msg);
      await setValues((current) => ({ ...current, resumeFileName: "", resumeText: "" }));
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
