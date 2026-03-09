// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useField } from "formik";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { FormError } from "./FormError";
import { cn } from "@/lib/utils";

interface FormikKeywordInputProps {
  name: string;
  placeholder?: string;
  label?: string;
  helpText?: string;
}

export function FormikKeywordInput({
  name,
  placeholder,
  label,
  helpText,
}: FormikKeywordInputProps) {
  const [field, meta] = useField(name);
  const showError = meta.touched && !!meta.error;

  const keywords = field.value
    ? field.value
        .split(",")
        .map((k: string) => k.trim())
        .filter(Boolean)
    : [];

  return (
    <div className="space-y-3">
      {label && (
        <label htmlFor={name} className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {label}
        </label>
      )}
      <Input
        id={name}
        {...field}
        placeholder={placeholder}
        className={cn(showError && "border-red-500 focus-visible:ring-red-500")}
      />
      {helpText && <p className="text-xs text-zinc-500">{helpText}</p>}
      {keywords.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {keywords.map((k: string) => (
            <Badge key={k} variant="secondary">
              {k}
            </Badge>
          ))}
        </div>
      )}
      {showError && <FormError message={meta.error} />}
    </div>
  );
}
