export type AnswerScope = { company: string; question: string; source_url: string };
const ANSWER_PREFIX = "Application answer (user-confirmed; use only for this company and exact question): ";

export function savedApplicationAnswer(rules: string, scope: AnswerScope): string | null {
  for (const line of rules.split("\n").reverse()) {
    if (!line.startsWith(ANSWER_PREFIX)) continue;
    try {
      const saved = JSON.parse(line.slice(ANSWER_PREFIX.length));
      if (saved.company === scope.company && saved.question === scope.question && typeof saved.answer === "string") return saved.answer;
    } catch { /* Preserve unrecognized existing rules. */ }
  }
  return null;
}

export function addApplicationAnswer(rules: string, scope: AnswerScope, answer: string): string {
  const trimmed = answer.trim();
  if (!trimmed) throw new Error("Enter an answer before saving.");
  if (trimmed.length > 4000) throw new Error("Keep your answer under 4,000 characters.");
  const retained = rules.split("\n").filter((line) => {
    if (!line.startsWith(ANSWER_PREFIX)) return true;
    try {
      const saved = JSON.parse(line.slice(ANSWER_PREFIX.length));
      return saved.company !== scope.company || saved.question !== scope.question;
    } catch { return true; }
  }).join("\n").trimEnd();
  const record = ANSWER_PREFIX + JSON.stringify({ ...scope, answer: trimmed });
  const result = retained ? `${retained}\n${record}` : record;
  if (result.length > 20000) throw new Error("Your application rules are full. Shorten them in Settings before saving this answer.");
  return result;
}

function indeedSourceUrl(value: string): string | null {
  if (/\s/.test(value)) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.username || url.password) return null;
    if (url.hostname !== "indeed.com" && !url.hostname.endsWith(".indeed.com")) return null;
    return url.href;
  } catch { return null; }
}

export function quickApplyRetryHref(sourceUrl: string): string | null {
  const safe = indeedSourceUrl(sourceUrl);
  return safe ? `/quick-apply?retry_job=${encodeURIComponent(safe)}` : null;
}

export function quickApplyInitialUrls(search: string, savedUrls: string): string {
  const params = new URLSearchParams(search);
  // An invalid retry must never fall back to a stale batch of saved jobs.
  return params.has("retry_job") ? indeedSourceUrl(params.get("retry_job") || "") || "" : savedUrls;
}
