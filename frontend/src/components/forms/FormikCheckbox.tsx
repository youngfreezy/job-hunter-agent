"use client";

import { useField } from "formik";

interface FormikCheckboxProps {
  name: string;
  label: string;
}

export function FormikCheckbox({ name, label }: FormikCheckboxProps) {
  const [field] = useField({ name, type: "checkbox" });

  return (
    <label className="flex items-center gap-2 text-sm cursor-pointer">
      <input
        type="checkbox"
        {...field}
        checked={field.value}
        className="rounded"
      />
      {label}
    </label>
  );
}
