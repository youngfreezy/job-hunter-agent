// Copyright (c) 2026 V2 Software LLC. All rights reserved.

"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import Link from "next/link";
import { Formik, Form } from "formik";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FormikInput } from "@/components/forms/FormikInput";
import { signupSchema, signupInitialValues } from "@/lib/schemas/auth";

export default function SignupPage() {
  const [error, setError] = useState("");

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950 flex items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <Link
            href="/"
            className="text-2xl font-bold tracking-tight mb-2 block"
          >
            JobHunter Agent
          </Link>
          <CardTitle className="text-lg">Create your account</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            variant="outline"
            className="w-full"
            onClick={() => signIn("google", { callbackUrl: "/session/new" })}
          >
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Continue with Google
          </Button>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-zinc-200 dark:border-zinc-800" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white dark:bg-zinc-950 px-2 text-zinc-500">
                or
              </span>
            </div>
          </div>

          <Formik
            initialValues={signupInitialValues}
            validationSchema={signupSchema}
            onSubmit={async (values, { setSubmitting }) => {
              setError("");
              const apiUrl =
                process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

              // 1. Register with the backend
              const regRes = await fetch(`${apiUrl}/api/auth/register`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  name: values.name,
                  email: values.email,
                  password: values.password,
                }),
              });

              if (!regRes.ok) {
                const data = await regRes.json().catch(() => ({}));
                setError(
                  data.detail || "Failed to create account. Please try again."
                );
                setSubmitting(false);
                return;
              }

              // 2. Sign in via NextAuth credentials
              const result = await signIn("credentials", {
                email: values.email,
                password: values.password,
                redirect: false,
              });

              if (result?.error) {
                setError(
                  "Account created but sign-in failed. Please try logging in."
                );
                setSubmitting(false);
              } else {
                window.location.href = "/session/new";
              }
            }}
          >
            {({ isSubmitting }) => (
              <Form className="space-y-3">
                <FormikInput name="name" placeholder="Full name" />
                <FormikInput name="email" type="email" placeholder="Email" />
                <FormikInput
                  name="password"
                  type="password"
                  placeholder="Password (min 8 characters)"
                />
                {error && <p className="text-sm text-red-500">{error}</p>}
                <Button
                  type="submit"
                  className="w-full"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Creating account..." : "Create Account"}
                </Button>
              </Form>
            )}
          </Formik>

          <p className="text-center text-sm text-zinc-500">
            Already have an account?{" "}
            <Link href="/auth/login" className="text-blue-600 hover:underline">
              Sign in
            </Link>
          </p>
          <p className="text-center text-xs text-zinc-400">
            By signing up, you agree to our Terms of Service and Privacy Policy.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
