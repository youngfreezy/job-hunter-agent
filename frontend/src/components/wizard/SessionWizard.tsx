"use client";

import { useState } from "react";
import { FormikProvider } from "formik";
import { usePersistedFormik } from "@/lib/hooks/usePersistedFormik";
import {
  sessionInitialValues,
  stepSchemas,
  type SessionFormValues,
} from "@/lib/schemas/session";
import { startSession } from "@/lib/api";
import { WizardStepper } from "./WizardStepper";
import { WizardNavigation } from "./WizardNavigation";
import { JobSearchStep } from "./steps/JobSearchStep";
import { ResumeProfileStep } from "./steps/ResumeProfileStep";
import { ReviewStep } from "./steps/ReviewStep";

const WIZARD_STEPS = [
  { label: "Job Search", description: "Keywords, locations, preferences" },
  { label: "Resume & Profile", description: "Resume and LinkedIn" },
  { label: "Review & Launch", description: "Confirm and start" },
];

export function SessionWizard() {
  const [step, setStep] = useState(0);
  const [submitError, setSubmitError] = useState("");

  const { formik } = usePersistedFormik<SessionFormValues>({
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
        const locationList = values.locations
          .split(",")
          .map((l) => l.trim())
          .filter(Boolean);

        const session = await startSession({
          keywords: keywordList,
          locations: locationList,
          remote_only: values.remoteOnly,
          salary_min: values.salaryMin ? parseInt(values.salaryMin) : null,
          resume_text: values.resumeText,
          linkedin_url: values.linkedinUrl || null,
          preferences: {},
        });

        // Use window.location.href instead of router.push() to avoid
        // Next.js dev-mode on-demand page compilation delay.
        window.location.href = `/session/${session.session_id}`;
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : "Failed to start session";
        if (
          msg === "Failed to fetch" ||
          msg.includes("NetworkError") ||
          msg === "Load failed"
        ) {
          setSubmitError(
            "Unable to connect to the server. Make sure the backend is running (npm start)."
          );
        } else {
          setSubmitError(msg);
        }
      }
    },
  });

  const handleNext = async () => {
    const currentSchema = stepSchemas[step];
    const fieldsToValidate = Object.keys(currentSchema.fields);

    // Touch all fields in current step to trigger error display
    const touchedFields = fieldsToValidate.reduce(
      (acc, field) => ({ ...acc, [field]: true }),
      {}
    );
    formik.setTouched({ ...formik.touched, ...touchedFields });

    try {
      await currentSchema.validate(formik.values, { abortEarly: false });
      setStep((prev) => Math.min(prev + 1, WIZARD_STEPS.length - 1));
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

  const stepComponents = [
    <JobSearchStep key="job-search" />,
    <ResumeProfileStep key="resume-profile" />,
    <ReviewStep key="review" onEditStep={setStep} />,
  ];

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
          isSubmitting={formik.isSubmitting}
        />
      </form>
    </FormikProvider>
  );
}
