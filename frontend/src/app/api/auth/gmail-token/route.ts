// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { type NextRequest } from "next/server";
import { getToken } from "next-auth/jwt";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * POST /api/auth/gmail-token
 *
 * Server-side proxy that reads Google OAuth tokens from the NextAuth JWT
 * and forwards them to the backend. This keeps tokens out of the browser
 * entirely — the client only sends the session_id.
 */
export async function POST(req: NextRequest) {
  if (process.env.ENABLE_GMAIL_VERIFICATION !== "true") {
    return Response.json({ status: "disabled" });
  }
  const token = await getToken({ req, secret: process.env.NEXTAUTH_SECRET });
  if (!token) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => null);
  const session_id = body?.session_id;
  if (typeof session_id !== "string" || !/^[a-zA-Z0-9-]{1,128}$/.test(session_id)) {
    return Response.json({ error: "session_id required" }, { status: 400 });
  }

  const googleAccessToken = token.googleAccessToken as string | undefined;
  if (!googleAccessToken) {
    return Response.json({ error: "No Google access token in session" }, { status: 400 });
  }

  // Reassemble chunked OAuth cookies just as NextAuth does.
  const sessionToken = await getToken({ req, secret: process.env.NEXTAUTH_SECRET, raw: true });

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
      client_id: process.env.GOOGLE_CLIENT_ID || undefined,
      client_secret: process.env.GOOGLE_CLIENT_SECRET || undefined,
    }),
  });

  if (!res.ok) {
    const detail = await res.text();
    return Response.json({ error: "Backend rejected token", detail }, { status: res.status });
  }

  return Response.json({ status: "ok" });
}
