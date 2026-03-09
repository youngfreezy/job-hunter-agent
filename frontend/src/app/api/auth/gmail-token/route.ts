// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { type NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";
import { cookies } from "next/headers";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * POST /api/auth/gmail-token
 *
 * Server-side proxy that reads Google OAuth tokens from the NextAuth JWT
 * and forwards them to the backend. This keeps tokens out of the browser
 * entirely — the client only sends the session_id.
 */
export async function POST(req: NextRequest) {
  const token = await getToken({ req, secret: process.env.NEXTAUTH_SECRET });
  if (!token) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { session_id } = await req.json();
  if (!session_id) {
    return Response.json({ error: "session_id required" }, { status: 400 });
  }

  const googleAccessToken = token.googleAccessToken as string | undefined;
  if (!googleAccessToken) {
    return Response.json({ error: "No Google access token in session" }, { status: 400 });
  }

  // Read the raw session cookie to forward as Authorization to the backend
  const cookieStore = await cookies();
  const sessionToken =
    cookieStore.get("next-auth.session-token")?.value ||
    cookieStore.get("__Secure-next-auth.session-token")?.value;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (sessionToken) {
    headers["Authorization"] = `Bearer ${sessionToken}`;
  }

  const res = await fetch(`${API_URL}/api/sessions/${session_id}/gmail-token`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      access_token: googleAccessToken,
      refresh_token: (token.googleRefreshToken as string) || undefined,
    }),
  });

  if (!res.ok) {
    const detail = await res.text();
    return Response.json({ error: "Backend rejected token", detail }, { status: res.status });
  }

  return Response.json({ status: "ok" });
}
