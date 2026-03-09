// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FormikProvider } from "formik";
import { usePersistedFormik } from "@/lib/hooks/usePersistedFormik";
import { sessionInitialValues, stepSchemas, type SessionFormValues } from "@/lib/schemas/session";
import { startSession } from "@/lib/api";
import { WizardStepper } from "./WizardStepper";
import { WizardNavigation } from "./WizardNavigation";
import { JobSearchStep } from "./steps/JobSearchStep";
import { ResumeProfileStep } from "./steps/ResumeProfileStep";
import { ConfigStep } from "./steps/ConfigStep";
import { ReviewStep } from "./steps/ReviewStep";

const WIZARD_STEPS = [
  { label: "Job Search", description: "Keywords, locations, preferences" },
  { label: "Resume & Profile", description: "Resume and LinkedIn" },
  { label: "Configure", description: "Job count, quality, mode" },
  { label: "Review & Launch", description: "Confirm and start" },
];

declare global {
  interface Window {
    umami?: { track: (event: string, data?: Record<string, unknown>) => void; identify: (data: Record<string, unknown>) => void };
  }
}

export function SessionWizard() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [submitError, setSubmitError] = useState("");
  const [isNavigating, setIsNavigating] = useState(false);

  useEffect(() => {
    window.umami?.track("wizard-start");
  }, []);

  const { formik, hydrated } = usePersistedFormik<SessionFormValues>({
    persistKey: "session_wizard",
    initialValues: sessionInitialValues,
    validationSchema: stepSchemas[step],
    onSubmit: async (values) => {
      setSubmitError("");
      try {
        const keywordList = values.keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean);
        const locationList = values.remoteOnly
          ? []
          : values.locations
              .split(",")
              .map((l) => l.trim())
              .filter(Boolean);

        const session = await startSession({
          keywords: keywordList,
          locations: locationList,
          remote_only: values.remoteOnly,
          salary_min: values.salaryMin ? parseInt(values.salaryMin) : null,
          search_radius: values.remoteOnly ? 100 : values.searchRadius,
          resume_text: values.resumeText,
          resume_file_path: values.resumeFilePath || null,
          linkedin_url: values.linkedinUrl || null,
          preferences: {},
          config: {
            max_jobs: values.maxJobs ?? 20,
            tailoring_quality: values.tailoringQuality ?? "standard",
            application_mode: values.applicationMode ?? "auto_apply",
            generate_cover_letters: values.generateCoverLetters ?? true,
            job_boards: values.jobBoards ?? ["linkedin", "indeed", "glassdoor", "ziprecruiter"],
          },
        });

        window.umami?.track("wizard-complete");
        setIsNavigating(true);
        router.push(`/session/${session.session_id}`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to start session";
        if (msg === "Failed to fetch" || msg.includes("NetworkError") || msg === "Load failed") {
          setSubmitError(
            "Unable to connect to the server. Make sure the backend is running (npm start)."
          );
        } else {
          setSubmitError(msg);
        }
        window.umami?.track("wizard-error", { error: msg });
      }
    },
  });

  const handleNext = async () => {
    const currentSchema = stepSchemas[step];
    const fieldsToValidate = Object.keys(currentSchema.fields);

    // Touch all fields in current step to trigger error display
    const touchedFields = fieldsToValidate.reduce((acc, field) => ({ ...acc, [field]: true }), {});
    formik.setTouched({ ...formik.touched, ...touchedFields });

    try {
      await currentSchema.validate(formik.values, { abortEarly: false });
      const nextStep = Math.min(step + 1, WIZARD_STEPS.length - 1);
      window.umami?.track("wizard-step", {
        step: WIZARD_STEPS[nextStep].label,
        number: nextStep + 1,
      });
      setStep(nextStep);
    } catch {
      // Validation errors display via FormError components
    }
  };

  const handleBack = () => {
    setStep((prev) => Math.max(prev - 1, 0));
  };

  const handleSubmit = () => {
    formik.submitForm();
  };

  // Live validation: disable Next/Submit when current step is invalid
  const isStepValid = useMemo(() => {
    try {
      stepSchemas[step].validateSync(formik.values, { abortEarly: true });
      return true;
    } catch {
      return false;
    }
  }, [step, formik.values]);

  const stepComponents = [
    <JobSearchStep key="job-search" />,
    <ResumeProfileStep key="resume-profile" />,
    <ConfigStep key="config" />,
    <ReviewStep key="review" onEditStep={setStep} />,
  ];

  if (!hydrated) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="flex gap-4 mb-8">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="flex-1 h-10 bg-muted rounded-lg" />
          ))}
        </div>
        <div className="space-y-4">
          <div className="h-5 w-32 bg-muted rounded" />
          <div className="h-10 w-full bg-muted rounded-lg" />
          <div className="h-5 w-24 bg-muted rounded" />
          <div className="h-10 w-full bg-muted rounded-lg" />
        </div>
      </div>
    );
  }

  return (
    <FormikProvider value={formik}>
      <WizardStepper steps={WIZARD_STEPS} currentStep={step} />

      <form onSubmit={(e) => e.preventDefault()} className="space-y-6">
        {stepComponents[step]}

        {submitError && (
          <div className="bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 rounded text-sm">
            {submitError}
          </div>
        )}

        <WizardNavigation
          currentStep={step}
          totalSteps={WIZARD_STEPS.length}
          onBack={handleBack}
          onNext={handleNext}
          onSubmit={handleSubmit}
          isSubmitting={formik.isSubmitting || isNavigating}
          isStepValid={isStepValid}
        />
      </form>
    </FormikProvider>
  );
}
