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
  resumeText: Yup.string().required(
    "Upload a resume file (.pdf, .docx, or .txt)."
  ),
  resumeFileName: Yup.string().default(""),
  resumeFilePath: Yup.string().default(""),
  linkedinUrl: Yup.string()
    .default("")
    .test(
      "valid-url",
      "Enter a valid LinkedIn URL (e.g. https://linkedin.com/in/yourprofile).",
      (value) => {
        if (!value || value === "") return true;
        try {
          const url = new URL(value);
          return url.hostname.includes("linkedin.com");
        } catch {
          return false;
        }
      }
    ),
});

// ---------- Step 3: Review (no additional validation) ----------
export const reviewSchema = Yup.object({});

// ---------- Combined schema (for type inference) ----------
export const sessionFormSchema = jobSearchSchema.concat(resumeProfileSchema);

// ---------- Type inference ----------
export type SessionFormValues = Yup.InferType<typeof sessionFormSchema>;

// ---------- Initial values ----------
export const sessionInitialValues: SessionFormValues = {
  keywords: "",
  locations: "",
  remoteOnly: false,
  salaryMin: "",
  resumeText: "",
  resumeFileName: "",
  resumeFilePath: "",
  linkedinUrl: "",
};

// ---------- Step schema map (indexed by step number) ----------
export const stepSchemas = [jobSearchSchema, resumeProfileSchema, reviewSchema];
