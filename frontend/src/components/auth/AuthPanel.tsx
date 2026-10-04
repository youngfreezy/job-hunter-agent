"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getProviders, signIn } from "next-auth/react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { safeAuthCallback } from "@/lib/auth-navigation";

export function AuthPanel({ signup = false }: { signup?: boolean }) {
  const params = useSearchParams();
  const fallback = signup ? "/session/new" : "/dashboard";
  const [callbackUrl, setCallbackUrl] = useState(fallback);
  const [providers, setProviders] = useState<{ google: boolean; demo: boolean } | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const requestedCallback = params.get("callbackUrl");
  const oauthError = params.get("error");

  useEffect(() => {
    setCallbackUrl(safeAuthCallback(requestedCallback, window.location.origin, fallback));
  }, [requestedCallback, fallback]);
  useEffect(() => {
    let active = true;
    getProviders().then((available) => {
      if (!active) return;
      setProviders({ google: !!available?.google, demo: !!available?.credentials });
      if (!available?.google && !available?.credentials) setError("Sign-in is temporarily unavailable. Please try again shortly.");
    }).catch(() => { if (active) setError("Unable to load sign-in. Please refresh and try again."); });
    return () => { active = false; };
  }, []);

  async function authenticate(provider: "google" | "credentials") {
    setPending(true);
    setError("");
    try {
      if (provider === "credentials") {
        const result = await signIn(provider, { email, password, callbackUrl, redirect: false });
        if (!result?.ok) throw new Error("The demo email or password is incorrect.");
        window.location.assign(callbackUrl);
      } else {
        window.umami?.track(signup ? "signup-google-clicked" : "login-google-clicked");
        await signIn(provider, { callbackUrl });
      }
    } catch (cause) {
      setError(provider === "credentials" && cause instanceof Error ? cause.message : "Unable to open Google sign-in. Please try again.");
    } finally {
      setPending(false);
    }
  }
  const message = error || (oauthError === "OAuthAccountNotLinked"
    ? "This email is already associated with another sign-in method."
    : oauthError ? "Sign-in could not be completed. Please try again." : "");
  const switchHref = `${signup ? "/auth/login" : "/auth/signup"}?callbackUrl=${encodeURIComponent(callbackUrl)}`;

  return <div className="min-h-screen bg-white dark:bg-zinc-950 flex items-center justify-center px-4">
    <Card className="w-full max-w-md">
      <CardHeader className="text-center">
        <Link href="/" className="text-2xl font-bold tracking-tight mb-2 block">JobHunter Agent</Link>
        <CardTitle className="text-lg">{signup ? "Create your account" : "Welcome back"}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {message && <p role="alert" className="text-sm text-red-600 dark:text-red-400 text-center">{message}</p>}
        {!signup && providers?.demo && <form className="space-y-3" onSubmit={(event) => { event.preventDefault(); void authenticate("credentials"); }}>
          <p className="text-sm text-zinc-500">Local demo sign-in</p>
          <label className="block text-sm">Demo email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} className="mt-1 w-full rounded-md border p-2 text-black" autoComplete="username" /></label>
          <label className="block text-sm">Demo password<input type="password" required value={password} onChange={(event) => setPassword(event.target.value)} className="mt-1 w-full rounded-md border p-2 text-black" autoComplete="current-password" /></label>
          <Button type="submit" disabled={pending} className="w-full">Sign in to local demo</Button>
        </form>}
        <Button variant="outline" className="w-full h-11 text-base" disabled={pending || !providers?.google} onClick={() => void authenticate("google")}>
          <svg aria-hidden="true" className="w-5 h-5 mr-2" viewBox="0 0 24 24">
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
          {pending ? "Opening sign-in…" : "Continue with Google"}
        </Button>
        <p className="text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
          {signup ? "Use your Google account to create your JobHunter account. " : "Sign in with Google to continue. "}
          Connect Indeed separately in Settings; verification codes can be entered in the live browser.
        </p>
        <p className="text-center text-sm text-zinc-500">
          {signup ? "Already have an account? " : "Don’t have an account? "}
          <Link href={switchHref} className="text-blue-600 dark:text-blue-400 hover:underline">{signup ? "Sign in" : "Sign up"}</Link>
        </p>
        {signup && <p className="text-center text-xs text-zinc-500">
          By signing up, you agree to our <Link className="underline" href="/terms">Terms of Service</Link> and <Link className="underline" href="/privacy">Privacy Policy</Link>.
        </p>}
      </CardContent>
    </Card>
  </div>;
}
