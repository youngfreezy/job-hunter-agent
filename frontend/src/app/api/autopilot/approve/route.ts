import { NextRequest } from "next/server";

/** Legacy email links only navigate. Session middleware and backend ownership checks
 * protect the destination; no token is forwarded and no work starts on GET/HEAD. */
export async function GET(request: NextRequest) {
  const sessionId = request.nextUrl.searchParams.get("session");
  const headers = { "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer" };
  if (!sessionId || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(sessionId)) {
    return Response.json({ error: "This review link is invalid. Open your Autopilot runs in the app." }, { status: 400, headers });
  }
  return new Response(null, { status: 303, headers: { ...headers, Location: `/session/${sessionId}` } });
}
