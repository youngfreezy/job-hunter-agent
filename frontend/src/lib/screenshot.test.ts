import { expect, it, vi, beforeEach } from 'vitest';
vi.mock('./api', () => ({API_BASE:'https://api.example.test', apiFetch:vi.fn(), getAuthHeaders:vi.fn(async()=>({Authorization:'Bearer test-session'}))}));
import { apiFetch } from './api';
import { loadSessionScreenshot } from './screenshot';
beforeEach(()=>vi.clearAllMocks());
it('authenticates screenshot requests without putting tokens in the URL', async()=>{
  vi.mocked(apiFetch).mockResolvedValue(new Response(new Blob(['image'],{type:'image/png'})));
  const signal=new AbortController().signal;
  await loadSessionScreenshot('session-id','shots/a b.png',signal);
  expect(apiFetch).toHaveBeenCalledWith('https://api.example.test/api/sessions/session-id/screenshot?path=shots%2Fa%20b.png',{headers:{Authorization:'Bearer test-session'},signal});
});
it('rejects failed screenshot responses instead of showing a broken image',async()=>{
  vi.mocked(apiFetch).mockResolvedValue(new Response('',{status:401}));
  await expect(loadSessionScreenshot('id','path',new AbortController().signal)).rejects.toThrow('Could not load');
});
