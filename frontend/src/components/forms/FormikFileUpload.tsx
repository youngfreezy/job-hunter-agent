"use client";

import { useFormikContext } from "formik";
import type { SessionFormValues } from "@/lib/schemas/session";

export function FormikFileUpload() {
  const { values, setFieldValue } = useFormikContext<SessionFormValues>();

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setFieldValue("resumeFileName", file.name);

    if (file.type === "text/plain" || file.name.endsWith(".txt")) {
      setFieldValue("resumeText", await file.text());
    } else if (
      file.type === "application/pdf" ||
      file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
      file.type === "application/msword"
    ) {
      try {
        const text = await file.text();
        if (text && !text.includes("\x00") && text.length < 500000) {
          setFieldValue("resumeText", text);
        } else {
          setFieldValue(
            "resumeText",
            `[File uploaded: ${file.name}]\n\nPlease also paste your resume text below for best results, or the AI will extract text from your uploaded file.`
          );
        }
      } catch {
        setFieldValue("resumeText", `[File uploaded: ${file.name}]`);
      }
    } else {
      e.target.value = "";
    }
  };

  return (
    <div>
      <div className="border-2 border-dashed border-zinc-300 dark:border-zinc-700 rounded-lg p-6 text-center">
        <input
          type="file"
          accept=".txt,.pdf,.doc,.docx"
          onChange={handleFileUpload}
          className="hidden"
          id="resume-upload"
        />
        <label htmlFor="resume-upload" className="cursor-pointer">
          <div className="text-sm text-zinc-600 dark:text-zinc-400">
            {values.resumeFileName ? (
              <span className="text-green-600 font-medium">{values.resumeFileName}</span>
            ) : (
              <>
                <span className="font-medium text-zinc-900 dark:text-white">Click to upload</span>
                {" "}or drag and drop
              </>
            )}
          </div>
          <p className="text-xs text-zinc-500 mt-1">.txt, .pdf, or .docx</p>
        </label>
      </div>
      {/* Error shown by FormikTextarea for resumeText field — don't duplicate */}
    </div>
  );
}
