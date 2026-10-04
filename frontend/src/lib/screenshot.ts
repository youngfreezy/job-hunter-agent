import { API_BASE, apiFetch, getAuthHeaders } from './api';

export async function loadSessionScreenshot(sessionId: string, path: string, signal: AbortSignal): Promise<Blob> {
  const response = await apiFetch(`${API_BASE}/api/sessions/${encodeURIComponent(sessionId)}/screenshot?path=${encodeURIComponent(path)}`, {
    headers: await getAuthHeaders(), signal,
  });
  if (!response.ok) throw new Error('Could not load this screenshot. Try again.');
  return response.blob();
}
