import { API_BASE, apiFetch, getAuthHeaders } from './api';
export interface ModelSettings { anthropic_key_set: boolean; anthropic_key_hint: string | null; provider: 'anthropic' | 'openai'; server_credentials_available: boolean; ready: boolean }
export async function modelSettings(key?: string): Promise<ModelSettings> {
  const response = await apiFetch(`${API_BASE}/api/model/settings`, {
    method: key === undefined ? 'GET' : 'PUT',
    headers: { ...await getAuthHeaders(), ...(key === undefined ? {} : {'Content-Type':'application/json'}) },
    ...(key === undefined ? {} : { body: JSON.stringify({anthropic_api_key:key}) }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Could not load or save model settings. Try again.');
  }
  return response.json();
}
