import { expect, it, vi, beforeEach } from 'vitest';
vi.mock('./api',()=>({API_BASE:'http://localhost:8000',getAuthHeaders:vi.fn(async()=>({Authorization:'Bearer fixture'})),apiFetch:vi.fn()}));
import { apiFetch } from './api';
import { modelBudgetAmount, modelSettings } from './model-settings';
beforeEach(()=>vi.clearAllMocks());
it('loads status without sending a key',async()=>{
 vi.mocked(apiFetch).mockResolvedValue(new Response(JSON.stringify({ready:false})));
 await modelSettings();
 expect(apiFetch).toHaveBeenCalledWith('http://localhost:8000/api/model/settings',{method:'GET',headers:{Authorization:'Bearer fixture'}});
});
it('distinguishes explicit deletion from keeping an existing key',async()=>{
 vi.mocked(apiFetch).mockResolvedValue(new Response(JSON.stringify({ready:false})));
 await modelSettings('');
 expect(vi.mocked(apiFetch).mock.calls[0][1]?.body).toBe('{"anthropic_api_key":""}');
});
it('surfaces rejected key storage without claiming success',async()=>{
 vi.mocked(apiFetch).mockResolvedValue(new Response(JSON.stringify({detail:'Invalid API key format'}),{status:400}));
 await expect(modelSettings('bad')).rejects.toThrow('Invalid API key format');
});

it('keeps owner settled usage and unresolved reservations distinct', async () => {
 const data = {funding:'server_demo', models:{default:'claude-sonnet-5-5',premium:'claude-sonnet-5-5',light:'claude-sonnet-5-5',browser:'anthropic/claude-sonnet-5-5'}, budget:{status:'available',currency:'USD',cap:'25.000000',settled:'11.400594',reserved:'3.515360',remaining:'10.084046'}};
 vi.mocked(apiFetch).mockResolvedValue(new Response(JSON.stringify(data)));
 expect(await modelSettings()).toEqual(data);
 expect(modelBudgetAmount(data.budget.remaining)).toBe('$10.084');
 expect(modelBudgetAmount('invalid')).toBe('Unavailable');
});
it('preserves an absent public-user ledger without inventing an allowance', async () => {
 vi.mocked(apiFetch).mockResolvedValue(new Response(JSON.stringify({funding:'own_keys',budget:null})));
 expect((await modelSettings()).budget).toBeNull();
});
