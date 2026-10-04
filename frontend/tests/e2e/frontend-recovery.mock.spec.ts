import { test, expect } from '@playwright/test';
import { encode } from 'next-auth/jwt';

// Every API request is intercepted. These tests cannot start provider sessions.
test.describe('Auxiliary recovery', () => {
  test.beforeEach(async ({ context }) => {
    const user = { id: 'audit-fixture', name: 'Fixture', email: 'fixture@example.test' };
    const token = await encode({ secret: process.env.NEXTAUTH_SECRET || 'ui-fixture-only-not-for-production', token: { sub: user.id, ...user }, maxAge: 3600 });
    await context.addCookies([{ name: 'next-auth.session-token', value: token, domain: 'localhost', path: '/', httpOnly: true, sameSite: 'Lax' }]);
    await context.addInitScript(() => {
      localStorage.setItem('jh_resume_text', 'Fixture Engineer. Experience building accessible software and reliable APIs.');
      localStorage.setItem('jh_resume_filename', 'original.pdf');
      localStorage.setItem('jh_resume_uuid', 'original-uuid');
      localStorage.setItem('jh_resume_bytes', btoa('original-pdf-bytes'));
      localStorage.setItem('jh_resume_saved_at', String(Date.now()));
    });
    await context.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname;
      let data: unknown = {}; let status = 200;
      if (path === '/api/auth/session') data = { user, expires: new Date(Date.now() + 3600000).toISOString() };
      else if (path === '/api/auth/token') data = { token: 'mock-token' };
      else if (path === '/api/auth/me') data = { user: { ...user, phone_verified: true, phone_number: '+15555550100', notification_channel: 'email', application_rules: '', wallet_balance: 3 } };
      else if (path.endsWith('/parse-resume')) data = { text: 'Fixture Engineer. Experience building accessible software and reliable APIs.', filename: 'original.pdf', resume_uuid: 'restored-uuid', file_path: '/mock/original.pdf' };
      else if (path === '/api/freelance' || path === '/api/auth/me/notification-channel') { status = 503; data = { detail: 'Fixture service unavailable. Try again.' }; }
      else if (path === '/api/browserbase/settings') data = { api_key_set: false, project_id: '', proxies: false, context_ids: {}, effective_configured: false, boards: ['indeed'], login_capture_boards: ['indeed'] };
      else if (path === '/api/model/settings') data = { ready: false, provider: 'anthropic', funding: 'own_keys', budget: null, models: {} };
      else if (path === '/api/billing/wallet') data = { balance: 3, is_premium: false };
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    });
  });

  const resultRoutes = ['/career-pivot/result','/interview-prep/result','/freelance/result','/session/main/career-pivot','/session/main/interview-prep'];
  for (const path of resultRoutes) test(`${path} denied stream offers reconnect without starting another session`,async({page,context})=>{
    let streams=0,starts=0;
    await context.route('**/api/**/stream',async route=>{streams++;await route.fulfill(streams===1?{status:403,json:{detail:'Access denied'}}:{contentType:'text/event-stream',body:'event: status\ndata: {"status":"completed"}\n\nevent: done\ndata: {}\n\n'});});
    for(const api of ['career-pivot','interview-prep'])await context.route(`**/api/${api}`,async route=>{starts++;await route.fulfill({json:{session_id:'fixture-result'}});});
    await page.goto(path);
    if(path==='/session/main/career-pivot')await page.getByRole('button',{name:'Start Free Assessment'}).click();
    if(path==='/session/main/interview-prep'){
      await page.getByPlaceholder('Company name',{exact:true}).fill('Fixture');await page.getByPlaceholder('Role title',{exact:true}).fill('Engineer');
      await page.getByRole('button',{name:/Start/}).last().click();
    }
    await expect(page.getByRole('alert').filter({hasText:/result connection/i})).toBeVisible({timeout:5000});
    const before=starts;await page.getByRole('button',{name:'Retry connection',exact:true}).click();
    await expect.poll(()=>streams,{timeout:5000}).toBeGreaterThan(1);expect(starts).toBe(before);
  });
  const lists=[['/marketplace','/api/marketplace/agents'],['/developer','/api/developer/api-keys'],['/autopilot','/api/autopilot/schedules'],['/billing','/api/billing/wallet'],['/apply','/api/sessions'],['/session/main/manual-apply','/api/sessions/main/application-log']];
  for(const [path,api] of lists)test(`${path} failed list is not an empty result`,async({page,context})=>{
    await context.route(`**${api}`,route=>route.fulfill({status:503,json:{detail:'Fixture unavailable'}}));
    await page.goto(path);await expect(page.getByRole('alert').filter({hasText:/could not load/i})).toBeVisible({timeout:5000});
    await expect(page.getByRole('button',{name:'Reload',exact:true})).toBeVisible();
    await expect(page.getByText(/No applications yet|No agents found|No API keys yet|No autopilot schedules yet/)).not.toBeVisible();
  });
  for (const path of ['/quick-apply', '/session/new']) test(`${path} failed cached attachment restore discards stale UUID`, async ({ page, context }) => {
    await context.route('**/api/**/parse-resume', route => route.fulfill({ status: 503, json: { detail: 'Fixture storage unavailable' } }));
    await page.goto(path);
    await expect(page.getByText('Could not restore the saved resume file. Please upload it again.')).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('jh_resume_uuid'))).toBeNull();
  });

});
