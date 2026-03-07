/**
 * HubSpot integration for pushing marketing copy to campaigns and landing
 * pages, and tracking copy performance.
 */

import { Client as HubSpotClient } from '@hubspot/api-client';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EmailCopyPayload {
  subject: string;
  previewText?: string;
  body: string;
}

export interface LandingPageCopyPayload {
  headline: string;
  subheadline?: string;
  body: string;
  cta?: string;
}

export interface CopyPerformanceMetrics {
  opens?: number;
  clicks?: number;
  conversions?: number;
  bounceRate?: number;
  /** Raw data returned from HubSpot for custom analysis. */
  raw: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// HubSpotIntegration
// ---------------------------------------------------------------------------

export class HubSpotIntegration {
  private client: HubSpotClient;

  /**
   * @param apiKey HubSpot private app access token.
   */
  constructor(apiKey: string) {
    if (!apiKey) {
      throw new Error(
        'HubSpotIntegration: apiKey is required. Pass your HubSpot private app access token.',
      );
    }
    this.client = new HubSpotClient({ accessToken: apiKey });
  }

  // -----------------------------------------------------------------------
  // pushToEmail
  // -----------------------------------------------------------------------

  /**
   * Push generated copy to a HubSpot marketing email.
   *
   * @param copy        The email copy payload.
   * @param campaignId  HubSpot campaign / email ID to update.
   */
  async pushToEmail(
    copy: EmailCopyPayload,
    campaignId: string,
  ): Promise<{ success: boolean; emailId: string }> {
    if (!campaignId) {
      throw new Error('HubSpotIntegration.pushToEmail: campaignId is required.');
    }

    try {
      // Use the transactional email API to update the email content.
      // The exact endpoint depends on HubSpot API version; this targets the
      // Marketing Emails API v3.
      const response = await this.client.apiRequest({
        method: 'PATCH',
        path: `/marketing/v3/emails/${campaignId}`,
        body: {
          subject: copy.subject,
          previewText: copy.previewText ?? '',
          content: {
            body: copy.body,
          },
        },
      });

      const data = (await response.json()) as Record<string, unknown>;

      return {
        success: true,
        emailId: String(data.id ?? campaignId),
      };
    } catch (error) {
      throw new Error(
        `HubSpotIntegration.pushToEmail failed: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // -----------------------------------------------------------------------
  // pushToLandingPage
  // -----------------------------------------------------------------------

  /**
   * Push generated copy to a HubSpot landing page.
   *
   * @param copy    The landing page copy payload.
   * @param pageId  HubSpot landing page ID to update.
   */
  async pushToLandingPage(
    copy: LandingPageCopyPayload,
    pageId: string,
  ): Promise<{ success: boolean; pageId: string }> {
    if (!pageId) {
      throw new Error(
        'HubSpotIntegration.pushToLandingPage: pageId is required.',
      );
    }

    try {
      const htmlContent = this.buildLandingPageHTML(copy);

      const response = await this.client.apiRequest({
        method: 'PATCH',
        path: `/cms/v3/pages/landing-pages/${pageId}`,
        body: {
          htmlTitle: copy.headline,
          metaDescription: copy.subheadline ?? '',
          layoutSections: {
            main: {
              type: 'rich_text',
              body: htmlContent,
            },
          },
        },
      });

      const data = (await response.json()) as Record<string, unknown>;

      return {
        success: true,
        pageId: String(data.id ?? pageId),
      };
    } catch (error) {
      throw new Error(
        `HubSpotIntegration.pushToLandingPage failed: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // -----------------------------------------------------------------------
  // trackCopyPerformance
  // -----------------------------------------------------------------------

  /**
   * Retrieve performance metrics for a piece of copy identified by its
   * HubSpot content ID (email or page).
   *
   * @param copyId  The HubSpot content ID.
   */
  async trackCopyPerformance(
    copyId: string,
  ): Promise<CopyPerformanceMetrics> {
    if (!copyId) {
      throw new Error(
        'HubSpotIntegration.trackCopyPerformance: copyId is required.',
      );
    }

    try {
      // Try the email statistics endpoint first.
      const response = await this.client.apiRequest({
        method: 'GET',
        path: `/marketing/v3/emails/${copyId}/statistics`,
      });

      const data = (await response.json()) as Record<string, unknown>;

      return {
        opens: typeof data.opens === 'number' ? data.opens : undefined,
        clicks: typeof data.clicks === 'number' ? data.clicks : undefined,
        conversions:
          typeof data.conversions === 'number' ? data.conversions : undefined,
        bounceRate:
          typeof data.bounceRate === 'number' ? data.bounceRate : undefined,
        raw: data,
      };
    } catch (error) {
      throw new Error(
        `HubSpotIntegration.trackCopyPerformance failed: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  // -----------------------------------------------------------------------
  // Private helpers
  // -----------------------------------------------------------------------

  private buildLandingPageHTML(copy: LandingPageCopyPayload): string {
    const parts: string[] = [];
    parts.push(`<h1>${this.escapeHTML(copy.headline)}</h1>`);
    if (copy.subheadline) {
      parts.push(`<h2>${this.escapeHTML(copy.subheadline)}</h2>`);
    }
    parts.push(`<div>${copy.body}</div>`);
    if (copy.cta) {
      parts.push(
        `<a href="#cta" class="cta-button">${this.escapeHTML(copy.cta)}</a>`,
      );
    }
    return parts.join('\n');
  }

  private escapeHTML(str: string): string {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}
