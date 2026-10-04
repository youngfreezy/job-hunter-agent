// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { getToken } from "next-auth/jwt";
import { NextRequest } from "next/server";

/**
 * GET /api/auth/token
 *
 * Returns the raw NextAuth session token (JWE) so the frontend can send it
 * as an Authorization: Bearer header to the backend API. The session cookie
 * is HttpOnly, so client-side JS cannot read it directly.
 */
export async function GET(request: NextRequest) {
  const headers = { "Cache-Control": "private, no-store" };
  const options = { req: request, secret: process.env.NEXTAUTH_SECRET };
  // NextAuth validates expiry and reassembles cookies split by large OAuth tokens.
  const session = await getToken(options);
  if (!session) {
    return Response.json({ error: "No session" }, { status: 401, headers });
  }
  const token = await getToken({ ...options, raw: true });
  return Response.json({ token }, { headers });
}
