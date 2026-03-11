// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Formik, Form, FormikProvider } from "formik";
import * as Yup from "yup";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormikFileUpload } from "@/components/forms/FormikFileUpload";
import { FormikInput } from "@/components/forms/FormikInput";
import { parseResumeTrial, startFreeTrialSession } from "@/lib/api";

// Simplified 3-step schema for free trial
const step1Schema = Yup.object({
  keywords: Yup.string()
    .required("Enter at least one keyword.")
    .test("has-keywords", "Enter at least one keyword.", (value) => {
      if (!value) return false;
      return value.split(",").map((k) => k.trim()).filter(Boolean).length > 0;
    }),
  locations: Yup.string().default(""),
  remoteOnly: Yup.boolean().default(false),
});

const step2Schema = Yup.object({
  resumeText: Yup.string()
    .required("Upload a resume file (.pdf, .docx, or .txt).")
    .test("has-email", "Your resume must include an email address.", (value) => {
      if (!value) return false;
      return /[\w.+-]+@[\w-]+\.[\w.-]+/.test(value);
    }),
  resumeFileName: Yup.string().default(""),
  resumeFilePath: Yup.string().default(""),
  resumeFileUuid: Yup.string().default(""),
  linkedinUrl: Yup.string().default(""),
});

const step3Schema = Yup.object({});

const stepSchemas = [step1Schema, step2Schema, step3Schema];

const fullSchema = step1Schema.concat(step2Schema);
type FormValues = Yup.InferType<typeof fullSchema> & {
  resumeFileName: string;
  resumeFilePath: string;
  resumeFileUuid: string;
  linkedinUrl: string;
};

const STEPS = ["Job Search", "Resume", "Launch"];

export default function FreeTrialPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [submitError, setSubmitError] = useState("");
  const [isNavigating, setIsNavigating] = useState(false);

  const initialValues: FormValues = {
    keywords: "",
    locations: "",
    remoteOnly: false,
    resumeText: "",
    resumeFileName: "",
    resumeFilePath: "",
    resumeFileUuid: "",
    linkedinUrl: "",
  };

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950">
      {/* Nav */}
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <Link href="/" className="text-lg font-bold text-zinc-900 dark:text-white">
            JobHunter Agent
          </Link>
          <Link
            href="/auth/signin"
            className="text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white"
          >
            Sign in
          </Link>
        </div>
      </nav>

      <div className="max-w-2xl mx-auto px-6 py-10">
        <div className="mb-2">
          <span className="inline-block bg-green-100 text-green-800 text-xs font-medium px-2.5 py-0.5 rounded-full dark:bg-green-900/40 dark:text-green-300">
            Free Trial
          </span>
        </div>
        <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
          Try JobHunter — No Account Required
        </h1>
        <p className="text-zinc-500 mt-1 mb-8">
          Upload your resume, tell us what you&apos;re looking for, and we&apos;ll apply to jobs for you.
        </p>

        {/* Stepper */}
        <div className="flex items-center mb-8">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center flex-1">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                  i <= step
                    ? "bg-blue-600 text-white"
                    : "bg-zinc-200 text-zinc-500 dark:bg-zinc-800"
                }`}
              >
                {i + 1}
              </div>
              <span className={`ml-2 text-sm ${i <= step ? "text-zinc-900 dark:text-white font-medium" : "text-zinc-400"}`}>
                {label}
              </span>
              {i < STEPS.length - 1 && (
                <div className={`flex-1 h-0.5 mx-3 ${i < step ? "bg-blue-600" : "bg-zinc-200 dark:bg-zinc-800"}`} />
              )}
            </div>
          ))}
        </div>

        {/* Warning banner */}
        <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
          <p className="text-sm text-amber-800 dark:text-amber-200">
            <span className="font-medium">Note:</span> Some job applications may require email verification codes.
            Without a connected email account, those applications will be skipped.{" "}
            <Link href="/auth/signin" className="underline font-medium">
              Sign up
            </Link>{" "}
            to enable auto-verification for all jobs.
          </p>
        </div>

        <Formik
          initialValues={initialValues}
          validationSchema={stepSchemas[step]}
          onSubmit={async (values) => {
            setSubmitError("");
            try {
              const keywordList = values.keywords.split(",").map((k) => k.trim()).filter(Boolean);
              const locationList = values.remoteOnly
                ? []
                : (values.locations || "").split(",").map((l) => l.trim()).filter(Boolean);

              const session = await startFreeTrialSession({
                keywords: keywordList,
                locations: locationList,
                remote_only: values.remoteOnly || false,
                salary_min: null,
                search_radius: 100,
                resume_text: values.resumeText || null,
                resume_file_path: values.resumeFilePath || null,
                resume_uuid: values.resumeFileUuid || null,
                linkedin_url: values.linkedinUrl || null,
                preferences: {},
                config: {
                  max_jobs: 5,
                  tailoring_quality: "standard",
                  application_mode: "auto_apply",
                  generate_cover_letters: true,
                  job_boards: ["linkedin", "indeed", "glassdoor", "ziprecruiter"],
                },
              });

              setIsNavigating(true);
              router.push(`/try/session/${session.session_id}`);
            } catch (err) {
              const msg = err instanceof Error ? err.message : "Failed to start session";
              setSubmitError(msg);
            }
          }}
        >
          {(formik) => {
            const isStepValid = (() => {
              try {
                stepSchemas[step].validateSync(formik.values, { abortEarly: true });
                return true;
              } catch {
                return false;
              }
            })();

            return (
              <FormikProvider value={formik}>
                <Form className="space-y-6">
                  {step === 0 && <Step1 />}
                  {step === 1 && <Step2 />}
                  {step === 2 && <Step3Review values={formik.values} />}

                  {submitError && (
                    <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded text-sm">
                      {submitError}
                    </div>
                  )}

                  <div className="flex justify-between pt-2">
                    {step > 0 ? (
                      <button
                        type="button"
                        onClick={() => setStep((s) => s - 1)}
                        className="px-5 py-2.5 text-sm font-medium text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      >
                        Back
                      </button>
                    ) : (
                      <div />
                    )}

                    {step < STEPS.length - 1 ? (
                      <button
                        type="button"
                        disabled={!isStepValid}
                        onClick={async () => {
                          const fields = Object.keys(stepSchemas[step].fields);
                          const touched = fields.reduce((acc, f) => ({ ...acc, [f]: true }), {});
                          formik.setTouched({ ...formik.touched, ...touched });
                          try {
                            await stepSchemas[step].validate(formik.values, { abortEarly: false });
                            setStep((s) => s + 1);
                          } catch {}
                        }}
                        className="px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Next
                      </button>
                    ) : (
                      <button
                        type="submit"
                        disabled={formik.isSubmitting || isNavigating}
                        className="px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {formik.isSubmitting || isNavigating ? "Starting..." : "Launch Free Trial"}
                      </button>
                    )}
                  </div>
                </Form>
              </FormikProvider>
            );
          }}
        </Formik>
      </div>
    </div>
  );
}

function Step1() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">What jobs are you looking for?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label className="text-sm font-medium block mb-1">Keywords</label>
          <FormikInput name="keywords" placeholder="e.g. Software Engineer, Full Stack, React" />
          <p className="text-xs text-zinc-500 mt-1">Separate multiple keywords with commas</p>
        </div>
        <div>
          <label className="text-sm font-medium block mb-1">Locations</label>
          <FormikInput name="locations" placeholder="e.g. San Francisco, New York, Remote" />
        </div>
      </CardContent>
    </Card>
  );
}

function Step2() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Your Resume</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <FormikFileUpload parseFn={parseResumeTrial} />
        <p className="text-xs text-zinc-500">
          We&apos;ll extract your name and email from your resume to personalize applications.
        </p>
      </CardContent>
    </Card>
  );
}

function Step3Review({ values }: { values: FormValues }) {
  const keywords = values.keywords.split(",").map((k) => k.trim()).filter(Boolean);
  const email = values.resumeText?.match(/[\w.+-]+@[\w-]+\.[\w.-]+/)?.[0] || "Not found";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Review & Launch</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-zinc-500 text-xs uppercase tracking-wide">Keywords</p>
            <p className="mt-1 font-medium">{keywords.join(", ")}</p>
          </div>
          <div>
            <p className="text-zinc-500 text-xs uppercase tracking-wide">Locations</p>
            <p className="mt-1 font-medium">{values.locations || "Remote"}</p>
          </div>
          <div>
            <p className="text-zinc-500 text-xs uppercase tracking-wide">Resume</p>
            <p className="mt-1 font-medium">{values.resumeFileName || "Uploaded"}</p>
          </div>
          <div>
            <p className="text-zinc-500 text-xs uppercase tracking-wide">Email (from resume)</p>
            <p className="mt-1 font-medium">{email}</p>
          </div>
        </div>

        <div className="rounded-xl bg-blue-50 p-4 dark:bg-blue-950/30">
          <p className="text-sm text-blue-800 dark:text-blue-200">
            <span className="font-medium">Free trial:</span> We&apos;ll search 4 job boards, score matches,
            and auto-apply to up to 5 jobs. This typically takes 10-20 minutes.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
