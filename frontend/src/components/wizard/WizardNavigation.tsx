"use client";

import { Button } from "@/components/ui/button";

interface WizardNavigationProps {
  currentStep: number;
  totalSteps: number;
  onBack: () => void;
  onNext: () => void;
  onSubmit: () => void;
  isSubmitting: boolean;
  isStepValid: boolean;
}

export function WizardNavigation({
  currentStep,
  totalSteps,
  onBack,
  onNext,
  onSubmit,
  isSubmitting,
  isStepValid,
}: WizardNavigationProps) {
  const isLastStep = currentStep === totalSteps - 1;

  return (
    <div className="flex justify-between mt-8">
      <Button
        type="button"
        variant="outline"
        onClick={onBack}
        disabled={currentStep === 0}
      >
        Back
      </Button>

      {isLastStep ? (
        <Button
          type="button"
          size="lg"
          onClick={onSubmit}
          disabled={!isStepValid}
          loading={isSubmitting}
        >
          Start Job Hunt Session
        </Button>
      ) : (
        <Button type="button" onClick={onNext} disabled={!isStepValid}>
          Next
        </Button>
      )}
    </div>
  );
}
