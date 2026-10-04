/** Validate every nonempty line; never silently drop an intended application. */
export function validateJobUrls(input: string, indeedOnly: boolean) {
  const urls: string[] = [];
  const errors: string[] = [];
  input.split(/\r?\n/).forEach((line, index) => {
    const value = line.trim();
    if (!value) return;
    try {
      const url = new URL(value);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || /\s/.test(value)) throw new Error();
      if (indeedOnly && (url.protocol !== 'https:' || (url.hostname !== 'indeed.com' && !url.hostname.endsWith('.indeed.com')))) {
        errors.push(`Line ${index + 1}: use an HTTPS Indeed listing. Employer redirects are excluded.`);
      } else if (!urls.includes(url.href)) urls.push(url.href);
    } catch { errors.push(`Line ${index + 1}: enter a complete job URL.`); }
  });
  return { urls, errors };
}
