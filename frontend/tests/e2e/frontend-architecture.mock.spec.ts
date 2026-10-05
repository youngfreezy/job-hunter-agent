import { expect, test } from '@playwright/test';
import { encode } from 'next-auth/jwt';

// All API requests are fixtures. This suite must never contact a model or employer.
test.beforeEach(async ({ context }) => {
  const user = { id: 'architecture-fixture', name: 'Fixture', email: 'fixture@example.test' };
  const token = await encode({ secret: process.env.NEXTAUTH_SECRET || 'ui-fixture-only-not-for-production', token: { sub: user.id, ...user }, maxAge: 3600 });
  await context.addCookies([{ name: 'next-auth.session-token', value: token, domain: 'localhost', path: '/', httpOnly: true, sameSite: 'Lax' }]);
  await context.addInitScript(() => {
    localStorage.setItem('jh_resume_text', 'Fixture Engineer. Reliable software and accessible products.');
    localStorage.setItem('jh_resume_filename', 'fixture.pdf');
    localStorage.setItem('jh_resume_bytes', btoa('fixture-pdf-bytes'));
    localStorage.setItem('jh_resume_saved_at', String(Date.now()));
  });
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown = {};
    if (path === '/api/auth/session') data = { user, expires: new Date(Date.now() + 3600000).toISOString() };
    else if (path === '/api/auth/token') data = { token: 'mock-token' };
    else if (path === '/api/auth/providers') data = { google: { id: 'google', name: 'Google' } };
    else if (path === '/api/auth/me') data = { user: { ...user, phone_verified: true, application_rules: '', wallet_balance: 3 } };
    else if (path.endsWith('/parse-resume')) data = { text: 'Fixture Engineer. Reliable software and accessible products.', filename: 'fixture.pdf', resume_uuid: 'fixture-resume', file_path: '/mock/fixture.pdf' };
    else if (path === '/api/billing/wallet') data = { balance: 3, is_premium: false };
    else if (path === '/api/career-pivot' || path === '/api/interview-prep') data = { session_id: 'fixture-result' };
    await route.fulfill({ json: data });
  });
});

test('Landing composition preserves navigation, analytics, FAQ and calculator interaction', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Land more interviews');
  await expect(page.locator('[data-umami-event="cta-try-free"][data-umami-event-location="nav"]')).toBeVisible();
  for (const id of ['pricing', 'how-it-works', 'faq', 'about']) await expect(page.locator(`#${id}`)).toBeAttached();
  const question = page.getByRole('button', { name: 'How does JobHunter Agent apply to jobs?' });
  await question.click();
  await expect(page.getByText(/Stagehand uses browser automation through Browserbase/)).toBeVisible();
  await question.click();
  await expect(page.getByText(/Stagehand uses browser automation through Browserbase/)).not.toBeVisible();
  await page.getByRole('slider').first().focus();
  await page.getByRole('slider').first().press('End');
  await expect(page.getByText('50.0 hours', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: /Watch the product demo/ })).toHaveAttribute('href', '/demo');
});

for (const path of ['/career-pivot/fixture-result', '/session/main/career-pivot']) {
  test(`${path} renders the shared risk and recommendations with working detail controls`, async ({ page, context }) => {
    const risk = { automation_risk_score: 25, task_breakdown: [], resistant_abilities: ['Judgment'], parsed_role: 'Fixture Engineer', parsed_skills: ['Design'], years_experience: 10, industry: 'Software' };
    const pivot = { role: 'Fixture Architect', skill_overlap_pct: 90, salary_range: { min: 200000, max: 300000, median: 250000 }, market_demand: 500, ai_risk_pct: 20, missing_skills: ['Strategy'], time_to_pivot_weeks: 4, skill_comparison: { categories: ['Design', 'Strategy'], user_scores: [90, 70], target_scores: [90, 90] }, learning_plan: [{ week: 1, topic: 'Architecture practice', resources: [{ name: 'Fixture course', hours: 2, cost: 'Free' }] }] };
    const stream = `event: risk_assessment\ndata: ${JSON.stringify(risk)}\n\nevent: pivot_roles\ndata: ${JSON.stringify({ recommended_pivots: [pivot] })}\n\nevent: done\ndata: {}\n\n`;
    await context.route('**/api/career-pivot/*/stream', route => route.fulfill({ contentType: 'text/event-stream', body: stream }));
    await page.goto(path);
    if (path.startsWith('/session/')) await page.getByRole('button', { name: 'Start Free Assessment' }).click();
    await expect(page.getByRole('heading', { name: 'Your AI Automation Risk' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '#1 Fixture Architect' })).toBeVisible();
    await page.getByText('View Learning Plan', { exact: true }).click();
    await expect(page.getByText('Week 1: Architecture practice', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'View Skill Comparison' }).click();
    await expect(page.getByRole('button', { name: 'Hide Skill Comparison' })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'Skills to New Industries' })).toBeDisabled();
  });
}

for (const path of ['/interview-prep/fixture-result', '/session/main/interview-prep']) {
  test(`${path} preserves shared coaching, graded answers, skip and report controls`, async ({ page, context }) => {
    const requests: string[] = [];
    const brief = { mission: 'Fixture mission', culture: 'Fixture culture', recent_news: '', glassdoor_rating: null, things_to_mention: [], interview_tips: [] };
    const questions = [{ id: 'q1', category: 'behavioral', question: 'Describe a reliable system you built.', source: 'fixture' }, { id: 'q2', category: 'technical', question: 'Explain your design choices.', source: 'fixture' }];
    await context.route('**/api/interview-prep/fixture-result**', async route => {
      const endpoint = new URL(route.request().url()).pathname.split('/').pop()!;
      if (route.request().method() === 'POST') requests.push(endpoint);
      if (endpoint === 'stream') return route.fulfill({ contentType: 'text/event-stream', body: `event: company_brief\ndata: ${JSON.stringify(brief)}\n\nevent: questions_ready\ndata: ${JSON.stringify({ questions })}\n\nevent: ready_for_practice\ndata: {}\n\n` });
      if (endpoint === 'coach') return route.fulfill({ json: { resume_highlights: ['Reliable systems experience'], star_scaffold: { situation: 'Context', task: 'Goal', action: 'Action', result: 'Outcome' }, key_points: [], pitfalls: [] } });
      if (endpoint === 'answer') return route.fulfill({ json: { grade: { question_id: 'q1', relevance: 8, specificity: 8, star_structure: 8, confidence: 8, overall: 8, feedback: 'Clear example', strong_answer_example: 'A concrete outcome' }, questions_answered: 1 } });
      if (endpoint === 'end') return route.fulfill({ json: { overall_readiness: 8, category_scores: {}, focus_areas: ['Add metrics'] } });
      return route.fulfill({ json: { paid: false } });
    });
    await page.goto(path);
    if (path.startsWith('/session/')) {
      await page.getByPlaceholder('Company name').fill('Fixture company');
      await page.getByPlaceholder('Role title').fill('Engineer');
      await page.getByRole('button', { name: 'Start Mock Interview' }).click();
    }
    await expect(page.getByText('Fixture mission')).toBeVisible();
    await page.getByRole('button', { name: 'Get AI Coaching' }).click();
    await expect(page.getByText('Reliable systems experience')).toBeVisible();
    await page.getByPlaceholder('Type your answer...').fill('I built a reliable service and measured the outcome.');
    await page.getByRole('button', { name: 'Submit Answer' }).click();
    await expect(page.getByRole('heading', { name: 'Score: 8/10' })).toBeVisible();
    await page.getByRole('button', { name: 'Skip', exact: true }).click();
    await expect(page.getByText('Explain your design choices.', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'End & See Report' }).click();
    await expect(page.getByRole('heading', { name: 'Readiness Report' })).toBeVisible();
    expect(requests).toEqual(['coach', 'answer', 'end']);
  });
}
