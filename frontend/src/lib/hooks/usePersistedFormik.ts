"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FormikConfig, FormikValues, useFormik } from "formik";

const STORAGE_PREFIX = "jh_form_";

interface UsePersistedFormikOptions<T extends FormikValues>
  extends FormikConfig<T> {
  persistKey: string;
  debounceMs?: number;
}

export function usePersistedFormik<T extends FormikValues>({
  persistKey,
  debounceMs = 300,
  initialValues,
  ...formikConfig
}: UsePersistedFormikOptions<T>) {
  const storageKey = `${STORAGE_PREFIX}${persistKey}`;
  const [hydrated, setHydrated] = useState(false);
  const hydratedRef = useRef(false);

  // Always start with initialValues to match server-rendered HTML
  const formik = useFormik<T>({
    ...formikConfig,
    initialValues,
    enableReinitialize: false,
  });

  // Hydrate from localStorage after mount
  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const parsed = JSON.parse(stored) as Partial<T>;
        const merged = { ...initialValues, ...parsed };
        formik.resetForm({ values: merged });
      }
    } catch {
      // Corrupted data -- ignore
    }
    setHydrated(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced persist on value changes (skip initial render before hydration)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!hydratedRef.current) return;

    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      try {
        const toStore = { ...formik.values };
        // Never persist resume text to localStorage (contains PII)
        if ("resumeText" in toStore) {
          (toStore as Record<string, unknown>).resumeText = "";
        }
        localStorage.setItem(storageKey, JSON.stringify(toStore));
      } catch {
        // localStorage full or unavailable
      }
    }, debounceMs);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [formik.values, storageKey, debounceMs]);

  const clearPersistedValues = useCallback(() => {
    try {
      localStorage.removeItem(storageKey);
    } catch {
      // ignore
    }
  }, [storageKey]);

  return { formik, clearPersistedValues, hydrated };
}
