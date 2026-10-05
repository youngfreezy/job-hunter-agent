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

  test('Quick Apply revalidates the attachment before launching and never reuses the saved UUID', async ({ page, context }) => {
    let requestBody: Record<string, unknown> | null = null;
    await context.route('**/api/sessions', async route => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({ status: 503, json: { detail: 'Fixture stopped after capturing launch payload' } });
    });
    await page.goto('/quick-apply');
    await expect(page.getByRole('button', { name: 'Change resume' })).toBeVisible();
    await page.getByLabel('Job URLs, one per line').fill('https://www.indeed.com/viewjob?jk=fixture');
    await page.getByRole('button', { name: 'Apply to 1 job', exact: true }).click();
    await expect.poll(() => requestBody).not.toBeNull();
    expect(requestBody).toMatchObject({ resume_uuid: 'restored-uuid', resume_file_path: '/mock/original.pdf' });
  });

  for (const path of ['/quick-apply', '/session/new']) test(`${path} corrupt cached bytes leave a usable upload control`, async ({ page, context }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await context.addInitScript(() => localStorage.setItem('jh_resume_bytes', '%%% invalid base64 %%%'));
    await page.goto(path);
    const input = page.locator(path === '/quick-apply' ? '#resume-upload-standalone' : '#resume-upload');
    await expect(input).toBeEnabled();
    await input.setInputFiles({ name: 'recovered.txt', mimeType: 'text/plain', buffer: Buffer.from('Recovered resume fixture@example.test') });
    await expect(page.getByText(path === '/quick-apply' ? 'Using recovered.txt' : 'recovered.txt', { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test('Quick Apply works with a current upload when browser storage is unavailable', async ({ page, context }) => {
    let requestBody: Record<string, unknown> | null = null;
    await context.addInitScript(() => Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Storage unavailable', 'SecurityError'); } }));
    await context.route('**/api/sessions', async route => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({ status: 503, json: { detail: 'Fixture stopped after capturing launch payload' } });
    });
    await page.goto('/quick-apply');
    await page.locator('#resume-upload-standalone').setInputFiles({ name: 'current.txt', mimeType: 'text/plain', buffer: Buffer.from('Current resume fixture@example.test') });
    await page.getByLabel('Job URLs, one per line').fill('https://www.indeed.com/viewjob?jk=fixture');
    await page.getByRole('button', { name: 'Apply to 1 job', exact: true }).click();
    await expect.poll(() => requestBody).not.toBeNull();
    expect(requestBody).toMatchObject({ resume_uuid: 'restored-uuid', resume_file_path: '/mock/original.pdf' });
  });

  test('Custom wizard restores text from the same attachment rather than an older form draft', async ({ page, context }) => {
    await context.addInitScript(() => localStorage.setItem('jh_form_session_wizard', JSON.stringify({
      keywords: 'AI Engineer', resumeText: 'STALE FORM RESUME old@example.test', resumeFileName: 'old.txt', resumeFileUuid: 'old-uuid',
    })));
    await page.goto('/session/new');
    await page.getByRole('button', { name: 'Custom Search', exact: true }).click();
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    await expect(page.locator('#resume-upload')).toBeEnabled();
    await page.getByText('Preview parsed text', { exact: true }).click();
    await expect(page.getByText('Fixture Engineer. Experience building accessible software and reliable APIs.', { exact: true })).toBeVisible();
    await expect(page.getByText('STALE FORM RESUME old@example.test', { exact: true })).not.toBeVisible();
  });

  for (const [path, buttonName, apiPath] of [
    ['/career-pivot', 'Start Assessment', '/api/career-pivot'],
    ['/interview-prep', 'Start Mock Interview', '/api/interview-prep'],
    ['/freelance', 'Generate sample briefs', '/api/freelance'],
  ]) test(`${path} uses the current upload even without browser storage`, async ({ page, context }) => {
    let requestBody: Record<string, unknown> | null = null;
    await context.addInitScript(() => Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Storage unavailable', 'SecurityError'); } }));
    await context.route(`**${apiPath}`, async route => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({ status: 503, json: { detail: 'Fixture stopped after capturing launch payload' } });
    });
    await page.goto(path);
    await page.locator('#resume-upload-standalone').setInputFiles({ name: 'current.txt', mimeType: 'text/plain', buffer: Buffer.from('Current resume fixture@example.test') });
    if (path === '/interview-prep') {
      await page.getByLabel('Company name', { exact: true }).fill('Fixture');
      await page.getByLabel('Role title', { exact: true }).fill('Engineer');
    }
    await page.getByRole('button', { name: buttonName, exact: true }).click();
    await expect.poll(() => requestBody).not.toBeNull();
    expect(requestBody).toMatchObject({ resume_text: 'Fixture Engineer. Experience building accessible software and reliable APIs.' });
    await expect(page.getByRole('button', { name: buttonName, exact: true })).toBeEnabled();
  });

  test('Parsed resume validation uses the same final values as its attachment', async ({ page, context }) => {
    await context.route('**/api/**/parse-resume', route => route.fulfill({json:{
      text:'Current Fixture Engineer fixture@example.test. Experience in software.', filename:'current.txt', resume_uuid:'current-uuid', file_path:'/mock/current.txt',
    }}));
    await page.goto('/session/new');
    await expect(page.locator('#resume-upload')).toBeEnabled();
    await expect(page.getByText('Upload a resume file (.pdf, .docx, or .txt).', {exact:true})).toHaveCount(0);
    await page.locator('#resume-upload').setInputFiles({name:'current.txt',mimeType:'text/plain',buffer:Buffer.from('Current Fixture Engineer fixture@example.test')});
    await expect(page.locator('#resume-upload')).toBeEnabled();
    await expect(page.getByText('Upload a resume file (.pdf, .docx, or .txt).', {exact:true})).toHaveCount(0);
    await expect(page.getByRole('alert').filter({hasText:/resume must include an email/})).toHaveCount(0);
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
