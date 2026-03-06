"use client";

import { useState } from "react";
import { useFormikContext } from "formik";
import type { SessionFormValues } from "@/lib/schemas/session";
import { parseResume } from "@/lib/api";

export function FormikFileUpload() {
  const { values, setFieldValue } = useFormikContext<SessionFormValues>();
  const [parsing, setParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setError(null);
    setFieldValue("resumeFileName", file.name);

    // Plain text files can be read directly
    if (file.type === "text/plain" || file.name.endsWith(".txt")) {
      setFieldValue("resumeText", await file.text());
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
      <div className="border-2 border-dashed border-zinc-300 dark:border-zinc-700 rounded-lg p-6 text-center">
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
          className={`cursor-pointer ${
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
      </div>
      {error && <p className="text-xs text-red-600 mt-1.5">{error}</p>}
    </div>
  );
}
