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
    const button = page.getByRole('button', { name: 'Generate sample briefs', exact: true });
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

  test('Shortlist requires individual review for unknown eligibility and blocks known failures', async ({ page, context }, testInfo) => {
    const scored = [
      { id: 'met', eligibility_status: 'met', eligibility_reasons: ['Required location and salary are supported.'] },
      { id: 'unknown', eligibility_status: 'unknown', eligibility_reasons: ['Office attendance requirement is unclear.'] },
      { id: 'blocked', eligibility_status: 'not_met', eligibility_reasons: ['Requires full-time office attendance.'] },
      { id: 'legacy' },
    ].map(({ id, ...eligibility }) => ({ job: { id, title: `${id} Engineer`, company: id, location: 'SF', board: 'indeed', url: 'https://www.indeed.com/viewjob?jk='+id }, score: 85, ...eligibility }));
    let approval: { approved_job_ids: string[] } | null = null;
    await context.route('**/api/sessions/eligibility-run**', async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith('/review')) { approval = route.request().postDataJSON(); return route.fulfill({ json: {} }); }
      if (path.endsWith('/stream')) return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' });
      return route.fulfill({ json: { session_id: 'eligibility-run', status: 'awaiting_review', keywords: ['Engineer'], locations: ['SF'], scored_jobs: scored, applications_submitted: [], applications_failed: [], session_config: {} } });
    });
    await page.goto('/session/eligibility-run');
    const dialog = page.getByRole('dialog', { name: 'Approve the shortlist' });
    const boxes = dialog.getByRole('checkbox');
    await expect(boxes).toHaveCount(4);
    await expect(boxes.nth(0)).toBeChecked();
    await expect(boxes.nth(1)).not.toBeChecked();
    await expect(boxes.nth(2)).toBeDisabled();
    await expect(boxes.nth(3)).not.toBeChecked();
    await expect(dialog.getByText('Search criteria need review', { exact: true })).toHaveCount(2);
    await expect(dialog.getByText('Office attendance requirement is unclear.')).toBeVisible();
    const list = await dialog.getByRole('group', { name: 'Jobs on the shortlist' }).boundingBox();
    const approve = await dialog.getByRole('button', { name: 'Approve 1 job', exact: true }).boundingBox();
    expect(list!.y + list!.height).toBeLessThanOrEqual(approve!.y);
    await page.screenshot({ path: testInfo.outputPath('eligibility-shortlist.png'), animations: 'disabled' });
    await boxes.nth(1).check();
    await dialog.getByRole('button', { name: 'Approve 2 jobs', exact: true }).click();
    await expect.poll(() => approval).toEqual({ approved_job_ids: ['met', 'unknown'], feedback: '' });
  });

  test('Stopped approved work keeps zero recorded results without claiming no approval', async ({ page, context }) => {
    await context.route('**/api/sessions/stopped-approved**', async route => {
      if (new URL(route.request().url()).pathname.endsWith('/stream')) return route.fulfill({ contentType: 'text/event-stream', body: ': connected\n\n' });
      return route.fulfill({ json: { session_id: 'stopped-approved', status: 'failed', keywords: ['Engineer'], locations: ['SF'], discovered_jobs: [{ id: 'job' }], scored_jobs: [{ job: { id: 'job', title: 'Engineer', company: 'Fixture', location: 'SF', board: 'indeed' }, score: 90 }], application_queue: ['job'], applications_submitted: [], applications_failed: [], applications_skipped: [], applications_used: 0, session_config: {} } });
    });
    await page.goto('/session/stopped-approved');
    const pipeline = page.getByRole('list', { name: 'Pipeline', exact: true });
    const apply = pipeline.getByRole('listitem').filter({ has: page.getByText('Apply', { exact: true }) });
    await expect(apply).toContainText('Stopped before an application result was recorded');
    await expect(apply.getByText('–', { exact: true })).toBeVisible();
    await expect(apply).not.toContainText(/0\s*attempted/);
    await expect(pipeline.getByRole('listitem').filter({ has: page.getByText('Report', { exact: true }) })).toContainText(/0\s*submitted/);
    await expect(page.getByLabel('Shortlist approval: approved', { exact: true })).toBeVisible();
    await expect(page.getByText('No jobs were approved', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Stopped · no submission confirmed', { exact: true })).toBeVisible();
  });

  test('Freelance examples disclose their source and never link to generated postings', async ({ page, context }) => {
    await page.goto('/freelance');
    await expect(page.getByText('AI-generated sample briefs for proposal practice. These are not live job listings; no marketplaces are searched.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Generate sample briefs', exact: true })).toBeVisible();
    const gigs = [{ id: 'sample', title: 'Sample dashboard project', platform: 'upwork', url: 'https://unverified.example/fake-job', client_name: 'Fabricated Client', posted_date: '1 minute ago', proposals_count: 17, match_score: 91, budget_type: 'fixed', budget_min: 1000, budget_max: 2000, duration: '2 weeks', description_snippet: 'Practice building a dashboard.' }];
    await context.route('**/api/freelance/sample/stream', route => route.fulfill({ contentType: 'text/event-stream', body: `event: gigs_found\ndata: ${JSON.stringify({ gigs })}\n\nevent: proposals_ready\ndata: ${JSON.stringify({ proposals: { sample: 'Practice proposal text.' } })}\n\nevent: done\ndata: {}\n\n` }));
    await page.goto('/freelance/sample');
    await expect(page.getByText('AI-generated sample briefs for proposal practice. These are not live job listings; no marketplaces are searched.')).toBeVisible();
    await expect(page.getByRole('heading', { name: '1 Sample Brief' })).toBeVisible();
    await expect(page.locator('a[href="https://unverified.example/fake-job"]')).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'View Posting' })).toHaveCount(0);
    await expect(page.getByText(/Fabricated Client|1 minute ago|17 proposals/)).toHaveCount(0);
    await page.getByRole('button', { name: 'View Proposal' }).click();
    await expect(page.getByText('Practice proposal text.', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Download practice proposal' })).toBeVisible();
  });

  test('Interview briefing is labeled AI-generated rather than live research', async ({ page, context }) => {
    await page.goto('/interview-prep');
    await expect(page.getByText(/AI-generated company briefing; verify current facts/)).toBeVisible();
    const brief = { mission: 'Fixture mission', culture: 'Fixture culture', recent_news: 'Unverified generated context', things_to_mention: [], interview_tips: [] };
    await context.route('**/api/interview-prep/sample/stream', route => route.fulfill({ contentType: 'text/event-stream', body: `event: company_brief\ndata: ${JSON.stringify(brief)}\n\nevent: ready_for_practice\ndata: {}\n\n` }));
    await page.goto('/interview-prep/sample');
    await expect(page.getByText(/AI-generated company briefing; verify current facts/)).toBeVisible();
    await expect(page.getByText('Researching company culture & values...')).toHaveCount(0);
  });

  test('Interview pipeline error shows recovery instead of an endless spinner', async ({ page, context }) => {
    await context.route('**/api/interview-prep/failed/stream', route => route.fulfill({ contentType: 'text/event-stream', body: 'event: status\ndata: {"status":"researching_company"}\n\nevent: error\ndata: {"message":"Company briefing could not be generated. Try again later."}\n\n' }));
    await page.goto('/interview-prep/failed');
    await expect(page.getByRole('alert').filter({ hasText: 'Company briefing could not be generated.' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry connection', exact: true })).toBeVisible();
    await expect(page.getByText('Generating an AI company briefing...', { exact: true })).toHaveCount(0);
  });

});
