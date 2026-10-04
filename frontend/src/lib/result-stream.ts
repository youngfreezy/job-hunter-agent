/** Server errors and transport errors need visible feedback, not an endless progress state. */
export function resultStreamError(event: Event): string {
  if (event instanceof MessageEvent) {
    try {
      const value = JSON.parse(event.data);
      if (typeof value.message === "string" && value.message.trim()) return value.message;
    } catch { /* A malformed error must still leave the progress state. */ }
  }
  return "The result connection was interrupted or access was denied. Check your sign-in, then reconnect to this existing result.";
}
