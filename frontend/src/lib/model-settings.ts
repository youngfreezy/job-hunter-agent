import { API_BASE, apiFetch, getAuthHeaders } from './api';
export type ModelBudget =
  | { status: 'available'; currency: 'USD'; cap: string; settled: string; reserved: string; remaining: string }
  | { status: 'unavailable' | 'not_configured' };
export interface ModelSettings {
  anthropic_key_set: boolean;
  anthropic_key_hint: string | null;
  provider: 'anthropic' | 'openai';
  server_credentials_available: boolean;
  ready: boolean;
  models?: { default: string; premium: string; light: string; browser: string };
  funding?: 'server_demo' | 'own_keys';
  budget?: ModelBudget | null;
}
export function modelBudgetAmount(value: string): string {
  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(amount)
    : 'Unavailable';
}
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
