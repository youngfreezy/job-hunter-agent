import { describe, expect, it } from 'vitest';
import { validateJobUrls } from './quick-apply-urls';
describe('Quick Apply URL validation', () => {
  it('rejects malformed lines instead of silently omitting intended jobs', () => {
    const result = validateJobUrls('https://indeed.com/viewjob?jk=one\nhttpbad\nnot a URL', true);
    expect(result.urls).toHaveLength(1);
    expect(result.errors).toHaveLength(2);
  });
  it('blocks employer, spoofed Indeed, credentials and insecure URLs in restricted mode', () => {
    for (const value of ['https://example.com/job', 'https://indeed.com.evil.test/job', 'https://x:secret@indeed.com/job', 'http://indeed.com/job']) {
      expect(validateJobUrls(value, true).errors).toHaveLength(1);
    }
  });
  it('accepts real Indeed subdomains and deduplicates exact URLs', () => {
    const url='https://www.indeed.com/viewjob?jk=one';
    expect(validateJobUrls(`${url}\n${url}`, true)).toEqual({urls:[url],errors:[]});
  });
  it('allows employer URLs when the restriction is disabled', () => {
    expect(validateJobUrls('https://jobs.example.com/job', false).errors).toEqual([]);
  });
});
