// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useField } from "formik";
import { Input } from "@/components/ui/input";
import { FormError } from "./FormError";
import { cn } from "@/lib/utils";

interface FormikInputProps {
  name: string;
  label?: string;
  placeholder?: string;
  type?: string;
  className?: string;
  disabled?: boolean;
}

export function FormikInput({ name, label, className, ...props }: FormikInputProps) {
  const [field, meta] = useField(name);
  const showError = meta.touched && !!meta.error;

  return (
    <div className="space-y-1">
      {label && (
        <label htmlFor={name} className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {label}
        </label>
      )}
      <Input
        id={name}
        {...field}
        {...props}
        className={cn(showError && "border-red-500 focus-visible:ring-red-500", className)}
      />
      {showError && <FormError message={meta.error} />}
    </div>
  );
}
