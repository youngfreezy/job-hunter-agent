/** Keep OAuth return paths on this site and out of authentication loops. */
export function safeAuthCallback(value: string | null, origin: string, fallback: string): string {
  if (!value || /[\\\u0000-\u0020]/.test(value) || value.startsWith("//")) return fallback;
  try {
    const url = new URL(value, origin);
    if (url.origin !== origin || !["http:", "https:"].includes(url.protocol)) return fallback;
    if (/^\/(?:auth|api\/auth)(?:\/|$)/.test(url.pathname)) return fallback;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return fallback;
  }
}
