// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import * as Yup from "yup";

// ---------- Step 1: Job Search ----------
export const jobSearchSchema = Yup.object({
  keywords: Yup.string()
    .required("Enter at least one keyword.")
    .test("has-keywords", "Enter at least one keyword.", (value) => {
      if (!value) return false;
      const parsed = value
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
      return parsed.length > 0;
    }),
  locations: Yup.string().default(""),
  remoteOnly: Yup.boolean().default(false),
  searchRadius: Yup.number().oneOf([10, 25, 50, 100, 150, 200]).default(100),
  salaryMin: Yup.string()
    .default("")
    .test("positive-salary", "Salary must be a positive number.", (value) => {
      if (!value || value === "") return true;
      const num = parseInt(value, 10);
      return !isNaN(num) && num > 0;
    }),
});

// ---------- Step 2: Resume & Profile ----------
export const resumeProfileSchema = Yup.object({
  resumeText: Yup.string()
    .required("Upload a resume file (.pdf, .docx, or .txt).")
    .test(
      "has-email",
      "Your resume must include an email address so employers can contact you.",
      (value) => {
        if (!value) return false;
        return /[\w.+-]+@[\w-]+\.[\w.-]+/.test(value);
      }
    ),
  resumeFileName: Yup.string().default(""),
  resumeFilePath: Yup.string().default(""),
  resumeFileUuid: Yup.string().default(""),
  linkedinUrl: Yup.string()
    .default("")
    .test(
      "valid-url",
      "Enter a valid LinkedIn URL (e.g. https://linkedin.com/in/yourprofile).",
      (value) => {
        if (!value || value === "") return true;
        try {
          const url = new URL(value);
          const host = url.hostname.toLowerCase();
          return host === "linkedin.com" || host.endsWith(".linkedin.com");
        } catch {
          return false;
        }
      }
    ),
});

// ---------- Step 3: Configuration ----------
export const configSchema = Yup.object({
  maxJobs: Yup.number().min(3).max(10).default(5),
  minimumSubmittedApplications: Yup.number()
    .min(0)
    .max(10)
    .test(
      "min-submitted-lte-max-jobs",
      "Minimum submitted applications cannot exceed jobs to apply to.",
      function (value) {
        const maxJobs = this.parent.maxJobs ?? 5;
        return (value ?? 0) <= maxJobs;
      }
    )
    .default(0),
  tailoringQuality: Yup.string().oneOf(["standard", "premium"]).default("standard"),
  applicationMode: Yup.string().oneOf(["auto_apply", "materials_only"]).default("auto_apply"),
  generateCoverLetters: Yup.boolean().default(true),
  jobBoards: Yup.array()
    .of(Yup.string().required())
    .default(["linkedin", "indeed", "glassdoor", "ziprecruiter"]),
});

// ---------- Step 4: Review (no additional validation) ----------
export const reviewSchema = Yup.object({});

// ---------- Combined schema (for type inference) ----------
export const sessionFormSchema = jobSearchSchema.concat(resumeProfileSchema).concat(configSchema);

// ---------- Type inference ----------
export type SessionFormValues = Yup.InferType<typeof sessionFormSchema>;

// ---------- Initial values ----------
export const sessionInitialValues: SessionFormValues = {
  keywords: "",
  locations: "",
  remoteOnly: false,
  searchRadius: 100,
  salaryMin: "",
  resumeText: "",
  resumeFileName: "",
  resumeFilePath: "",
  resumeFileUuid: "",
  linkedinUrl: "",
  maxJobs: 5,
  minimumSubmittedApplications: 0,
  tailoringQuality: "standard",
  applicationMode: "auto_apply",
  generateCoverLetters: true,
  jobBoards: ["linkedin", "indeed", "glassdoor", "ziprecruiter"],
};

// ---------- Step schema map (indexed by step number) ----------
export const stepSchemas = [jobSearchSchema, resumeProfileSchema, configSchema, reviewSchema];
