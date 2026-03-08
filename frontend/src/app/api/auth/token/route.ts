// Copyright (c) 2026 V2 Software LLC. All rights reserved.

import { cookies } from "next/headers";

/**
 * GET /api/auth/token
 *
 * Returns the raw NextAuth session token (JWE) so the frontend can send it
 * as an Authorization: Bearer header to the backend API. The session cookie
 * is HttpOnly, so client-side JS cannot read it directly.
 */
export async function GET() {
  const cookieStore = await cookies();
  const token =
    cookieStore.get("next-auth.session-token")?.value ||
    cookieStore.get("__Secure-next-auth.session-token")?.value;

  if (!token) {
    return Response.json({ error: "No session" }, { status: 401 });
  }

  return Response.json({ token });
}
