import { expect, it, vi, beforeEach } from 'vitest';
vi.mock('./api',()=>({API_BASE:'http://localhost:8000',getAuthHeaders:vi.fn(async()=>({Authorization:'Bearer fixture'})),apiFetch:vi.fn()}));
import { apiFetch } from './api';
import { modelSettings } from './model-settings';
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
