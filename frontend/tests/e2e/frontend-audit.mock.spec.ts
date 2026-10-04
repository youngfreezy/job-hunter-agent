import { test, expect } from '@playwright/test';
import { encode } from 'next-auth/jwt';

// Every API request is intercepted. These tests cannot start provider sessions.
test.describe('Mocked frontend recovery and resume identity', () => {
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
      else if (path.endsWith('/parse-resume')) {
        const body=route.request().postData() || '';
        const name=body.includes('replacement.txt')?'replacement.txt':body.includes('current.txt')?'current.txt':'original.pdf';
        data={text:name==='current.txt'?'Current Fixture Engineer fixture@example.test. Experience in applied AI.':'Fixture Engineer fixture@example.test. Experience building accessible software.',filename:name,resume_uuid:name+'-uuid',file_path:'/mock/'+name};
      }
      else if (path === '/api/freelance' || path === '/api/auth/me/notification-channel') { status = 503; data = { detail: 'Fixture service unavailable. Try again.' }; }
      else if (path === '/api/browserbase/settings') data = { api_key_set: false, project_id: '', proxies: false, context_ids: {}, effective_configured: false, boards: ['indeed'], login_capture_boards: ['indeed'] };
      else if (path === '/api/model/settings') data = { ready: false, provider: 'anthropic', funding: 'own_keys', budget: null, models: {} };
      else if (path === '/api/billing/wallet') data = { balance: 3, is_premium: false };
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    });
  });
  test('Freelance start failure leaves a usable retry and backend explanation', async ({ page }) => {
    await page.goto('/freelance');
    const button = page.getByRole('button', { name: 'Start Searching', exact: true });
    await button.click();
    await expect(button).toBeEnabled({ timeout: 4000 });
    await expect(page.getByText('Fixture service unavailable. Try again.', { exact: true })).toBeVisible();
  });
  test('Notification failure does not claim the new channel was saved', async ({ page }) => {
    await page.goto('/settings');
    await page.locator('input[type="radio"][value="sms"]').click();
    await expect(page.locator('input[type="radio"][value="email"]')).toBeChecked({ timeout: 4000 });
    await expect(page.getByText(/Couldn.t save the notification preference/)).toBeVisible();
  });
  for (const [route, id] of [['/quick-apply', 'resume-upload-standalone'], ['/session/new', 'resume-upload']] as const) {
    test(`${route} TXT replacement uploads its own attachment and invalidates the previous PDF`, async ({ page }) => {
      await page.goto(route);
      if (route === '/quick-apply') await page.getByRole('button', { name: 'Change resume' }).click();
      const input = page.locator('#' + id);
      await expect(input).toBeEnabled();
      await input.setInputFiles({ name: 'replacement.txt', mimeType: 'text/plain', buffer: Buffer.from('Replacement Engineer. Different applicant content, never use the old PDF.') });
      await expect(page.getByText(/^(Using )?replacement\.txt$/)).toBeVisible();
      await expect.poll(() => page.evaluate(() => localStorage.getItem('jh_resume_uuid'))).toBe('replacement.txt-uuid');
      const attachment = await page.evaluate(() => ({ bytes: localStorage.getItem('jh_resume_bytes'), uuid: localStorage.getItem('jh_resume_uuid') }));
      expect(attachment.uuid).toBe('replacement.txt-uuid');
      expect(Buffer.from(attachment.bytes!, 'base64').toString()).toContain('Replacement Engineer');
      expect(Buffer.from(attachment.bytes!, 'base64').toString()).not.toContain('original-pdf-bytes');
    });
  }
  for (const route of ['/apply', '/session/audit-run/manual-apply']) {
    test(`${route} separates uncertain delivery and downloads saved materials`, async ({ page, context }) => {
      await context.route('**/api/sessions', route => route.fulfill({json: [{session_id: 'audit-run', status: 'completed', keywords: ['Engineer'], locations: ['SF'], applications_submitted: 0, applications_failed: 0, applications_uncertain: 1, created_at: new Date().toISOString()}]}));
      await context.route('**/api/sessions/audit-run', route => route.fulfill({json: {session_id: 'audit-run', status: 'completed', keywords: ['Engineer'], locations: ['SF'], applications_submitted: [], applications_failed: [], scored_jobs: [], session_config: {}}}));
      await context.route('**/application-log', route => route.fulfill({json: {entries: [{status: 'failed', error_category: 'submission_uncertain', job: {id: 'job1', title: 'Engineer', company: 'Fixture', url: 'https://www.indeed.com/viewjob?jk=fixture'}, error: 'Receipt unavailable', cover_letter: 'Dear hiring team, this is a fixture cover letter.', tailored_resume: {tailored_text: 'Fixture Engineer\nSoftware experience', fit_score: 80, changes_made: []}, duration: 60, submitted_at: null, screenshot_path: '/tmp/fixture.png'}]}}));
      await context.route('**/screenshot?*', async route => {
        expect(route.request().headers().authorization).toBe('Bearer mock-token');
        await route.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64')});
      });
      await page.goto(route);
      await expect(page.getByText('Confirmation pending—check before retrying',{exact: true})).toBeVisible();
      await expect(page.getByRole('button', {name: 'Check application', exact: true})).toBeVisible();
      await expect(page.getByRole('button', {name: 'Failed (0)', exact: true})).toBeVisible();
      const download = page.waitForEvent('download');
      await page.getByRole('button', {name: /Cover Letter PDF/}).first().click();
      expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
      const resumeDownload=page.waitForEvent('download');
      await page.getByRole('button',{name:/Resume PDF/}).first().click();
      expect((await resumeDownload).suggestedFilename()).toMatch(/\.pdf$/);
      await page.getByRole('button',{name:/View application screenshot/}).click();
      await expect(page.getByRole('img',{name:'Application screenshot'})).toBeVisible();
    });
  }
  test('Authenticated stream renders progress; Pause and Stop send their explicit controls', async ({ page, context }) => {
    const state = {session_id: 'control-run', status: 'applying', keywords: ['Engineer'], locations: ['SF'], applications_submitted: [], applications_failed: [], scored_jobs: [], session_config: {}};
    const requests: {path: string; body: unknown}[] = [];
    await context.route('**/api/sessions/control-run**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname;
      if (path.endsWith('/stream')) {
        expect(new URL(request.url()).searchParams.has('token')).toBe(false);
        expect(request.headers().authorization).toBe('Bearer mock-token');
        return route.fulfill({headers:{'Access-Control-Allow-Origin':'*'},contentType: 'text/event-stream',body: 'event: application_progress\ndata: {"status":"applying","step":"Fixture authenticated browser action"}\n\n'});
      }
      if(request.method() === 'POST') requests.push({path, body: request.postData() ? request.postDataJSON() : null});
      return route.fulfill({json: path === '/api/sessions/control-run' ? state : {status:'ok', message:'Fixture accepted'}});
    });
    await page.goto('/session/control-run');
    await expect(page.getByText('Fixture authenticated browser action', {exact: true})).toBeVisible({timeout:5000});
    await page.getByRole('button', {name:'Pause',exact:true}).click();
    await expect.poll(()=>requests.some(r=>r.path.endsWith('/steer'))).toBe(true);
    await page.getByRole('button', {name:'Stop run',exact:true}).click();
    await page.getByRole('dialog').getByRole('button', {name:'Stop run',exact:true}).click();
    await expect.poll(()=>requests.some(r=>r.path.endsWith('/kill'))).toBe(true);
  });
  test('Coach approval failure stays reviewable and can be retried', async ({ page, context }) => {
    let failures = 1;
    const coach = {rewritten_resume:'Fixture coached resume',cover_letter_template:'Fixture letter',linkedin_advice:[],confidence_message:'Fixture feedback',key_strengths:[],improvement_areas:[],resume_score:{overall:80,keyword_density:80,impact_metrics:80,ats_compatibility:80,readability:80,formatting:80,feedback:[]}};
    await context.route('**/api/sessions/coach-run**', async route => {
      const path = new URL(route.request().url()).pathname;
      if(path.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:': connected\n\n'});
      if(path.endsWith('/coach-review'))return route.fulfill({status: failures-- > 0 ? 503 : 200,json:{detail:'Fixture approval unavailable',status:'ok'}});
      return route.fulfill({json:{session_id:'coach-run',status:'awaiting_coach_review',keywords:['Engineer'],locations:['SF'],coach_output:coach,scored_jobs:[],applications_submitted:[],applications_failed:[],session_config:{}}});
    });
    await page.goto('/session/coach-run');
    const dialog = page.getByRole('dialog');
    const keep = dialog.getByRole('button',{name:/Keep my original/});
    await keep.click();
    await expect(page.getByText(/Failed to submit coach review|Fixture approval unavailable/)).toBeVisible();
    await expect(keep).toBeEnabled();
    await keep.click();
    await expect(dialog).not.toBeVisible();
  });
  test('Required question save persists an exact scoped answer and only prefills a single retry', async ({page,context})=>{
    let rules='Existing fixture rule'; let starts=0;
    await context.route('**/api/auth/me/application-rules',async route=>{if(route.request().method()==='PUT')rules=route.request().postDataJSON().application_rules;await route.fulfill({json:{application_rules:rules}});});
    await context.route('**/api/sessions',async route=>{if(route.request().method()==='POST')starts++;await route.fulfill({json:[]});});
    await context.route('**/api/sessions/question-run**',async route=>{
      if(new URL(route.request().url()).pathname.endsWith('/stream'))return route.fulfill({contentType:'text/event-stream',body:': connected\n\n'});
      return route.fulfill({json:{session_id:'question-run',status:'completed',keywords:['Engineer'],locations:['SF'],scored_jobs:[],applications_submitted:[],applications_failed:[],session_config:{},application_questions:{job1:{question:'Do you hold a fixture certificate?',company:'Fixture Co',title:'Engineer',source_url:'https://www.indeed.com/viewjob?jk=fixture',application_url:'https://www.indeed.com/viewjob?jk=fixture'}}}});
    });
    await page.goto('/session/question-run');
    await page.getByLabel('Your answer',{exact:true}).fill('No');await page.getByRole('button',{name:'Save answer',exact:true}).click();
    await expect(page.getByRole('link',{name:'Retry this job'})).toBeVisible();
    expect(rules).toContain('Existing fixture rule');expect(rules).toContain('Fixture Co');expect(rules).toContain('Do you hold a fixture certificate?');
    await page.getByRole('link',{name:'Retry this job'}).click();
    await expect(page.getByLabel('Job URLs, one per line')).toHaveValue('https://www.indeed.com/viewjob?jk=fixture');expect(starts).toBe(0);
  });

  test('Custom wizard launches one job with the current resume and explicit preferences',async({page,context})=>{
    let payload: Record<string, unknown>|null=null;
    await context.route('**/api/sessions',async route=>{payload=route.request().postDataJSON();await route.fulfill({json:{session_id:'custom-run'}});});
    await context.route('**/api/sessions/custom-run**',route=>route.fulfill({json:{session_id:'custom-run',status:'completed',keywords:['AI Engineer'],locations:['SF'],scored_jobs:[],applications_submitted:[],applications_failed:[],session_config:{}}}));
    await page.goto('/session/new');await page.getByRole('button',{name:'Custom Search',exact:true}).click();
    await page.getByPlaceholder('e.g. React, Senior Engineer, Data Scientist, Nurse Practitioner').fill('Senior Applied AI Engineer');
    await page.getByPlaceholder('e.g. San Francisco, New York, Austin').fill('San Francisco');
    await page.locator('[name=salaryMin]').fill('220000');
    await page.getByRole('button',{name:'Next',exact:true}).click();
    await expect(page.locator('#resume-upload')).toBeEnabled();
    await page.locator('#resume-upload').setInputFiles({name:'current.txt',mimeType:'text/plain',buffer:Buffer.from('Current Fixture Engineer fixture@example.test. Experience in applied AI software systems. Skills Python and TypeScript. Education BS Computer Science.')});
    await page.getByRole('button',{name:'Next',exact:true}).click();
    await page.getByRole('button',{name:'Next',exact:true}).click();
    await page.getByRole('button',{name:'Start Job Hunt Session',exact:true}).click();
    await expect.poll(()=>payload).not.toBeNull();
    expect(payload).toMatchObject({keywords:['Senior Applied AI Engineer'],locations:['San Francisco'],salary_min:220000,preferences:{search_input_mode:'structured'},resume_uuid:'current.txt-uuid',resume_file_path:'/mock/current.txt',config:{max_jobs:1,job_boards:['indeed']}});
    expect(String(payload!.resume_text)).toContain('Current Fixture Engineer');
  });

  test('New Search fits a 320px viewport in Quick and Custom modes', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 812 });
    await page.goto('/session/new');
    await expect(page.getByLabel('Describe your job search')).toBeVisible();
    const overflow = () => page.evaluate(() => [...document.querySelectorAll('body *')].map(el => ({tag:el.tagName,cls:el.className,text:el.textContent?.slice(0,60),right:el.getBoundingClientRect().right})).filter(el => el.right > innerWidth + 1));
    expect(await overflow()).toEqual([]);
    await page.getByRole('button', { name: 'Custom Search', exact: true }).click();
    expect(await overflow()).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('custom-320.png'), fullPage: true });
  });

});
