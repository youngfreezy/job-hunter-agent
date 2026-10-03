import { expect, it } from 'vitest';
import { jobSearchSchema } from './session';
it('accepts a discovery prompt without separate keywords', async () => {
 await expect(jobSearchSchema.validate({ keywords: '', discoveryPrompt: 'Find applied AI roles in San Francisco, hybrid or remote.' })).resolves.toBeTruthy();
});
it('still rejects an empty search', async () => {
 await expect(jobSearchSchema.validate({ keywords: '', discoveryPrompt: '' })).rejects.toThrow();
});
