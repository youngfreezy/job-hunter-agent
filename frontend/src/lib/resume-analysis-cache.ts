import type { ResumeAnalysis } from './api';
async function key(text: string) {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return 'jh_resume_analysis_v1_' + Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
}
export async function readResumeAnalysis(text: string): Promise<ResumeAnalysis | null> {
  try {
    const result = JSON.parse(localStorage.getItem(await key(text)) || 'null');
    return result && Array.isArray(result.keywords) && result.keywords.every((v: unknown) => typeof v === 'string') && Array.isArray(result.locations) && result.locations.every((v: unknown) => typeof v === 'string') ? result : null;
  } catch { return null; }
}
export async function saveResumeAnalysis(text: string, result: ResumeAnalysis) {
  try { localStorage.setItem(await key(text), JSON.stringify(result)); } catch { /* Analysis still works when storage is unavailable. */ }
}
