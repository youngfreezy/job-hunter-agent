/** Preserve actionable API validation/setup messages without assuming a JSON response. */
export async function responseError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  return typeof body?.detail === "string" && body.detail.trim() ? body.detail : fallback;
}
