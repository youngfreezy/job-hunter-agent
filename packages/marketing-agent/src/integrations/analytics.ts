/**
 * Generic analytics integration for tracking copy variant performance.
 *
 * Provides a provider-agnostic interface that can connect to Mixpanel, GA4,
 * Segment, or any custom analytics backend.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AnalyticsProvider = 'mixpanel' | 'ga4' | 'segment' | 'custom';

export interface AnalyticsConfig {
  /** Analytics provider to use. */
  provider: AnalyticsProvider;
  /** API key or measurement ID for the provider. */
  apiKey: string;
  /** Optional base URL for custom analytics backends. */
  baseUrl?: string;
  /** Optional additional headers for API requests. */
  headers?: Record<string, string>;
}

export interface VariantMetrics {
  impressions?: number;
  clicks?: number;
  conversions?: number;
  bounceRate?: number;
  timeOnPage?: number;
  scrollDepth?: number;
  [key: string]: number | undefined;
}

export interface TopPerformingResult {
  variantId: string;
  pageType: string;
  conversionRate: number;
  metrics: VariantMetrics;
}

export interface ConversionEvent {
  copyId: string;
  event: string;
  timestamp: string;
  value?: number;
  metadata?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// AnalyticsIntegration
// ---------------------------------------------------------------------------

export class AnalyticsIntegration {
  private config: AnalyticsConfig;

  constructor(config: AnalyticsConfig) {
    if (!config.apiKey) {
      throw new Error(
        'AnalyticsIntegration: apiKey is required in the config.',
      );
    }
    if (!config.provider) {
      throw new Error(
        'AnalyticsIntegration: provider is required in the config.',
      );
    }
    this.config = config;
  }

  // -----------------------------------------------------------------------
  // trackCopyVariant
  // -----------------------------------------------------------------------

  /**
   * Track metrics for a specific copy variant. Call this whenever you have
   * new performance data (e.g. from a webhook or batch job).
   *
   * @param variantId  Unique identifier for the copy variant.
   * @param metrics    Performance metrics to record.
   */
  async trackCopyVariant(
    variantId: string,
    metrics: VariantMetrics,
  ): Promise<{ success: boolean; eventId: string }> {
    if (!variantId) {
      throw new Error(
        'AnalyticsIntegration.trackCopyVariant: variantId is required.',
      );
    }

    const payload = {
      event: 'copy_variant_metrics',
      variantId,
      metrics,
      timestamp: new Date().toISOString(),
    };

    return this.sendEvent(payload);
  }

  // -----------------------------------------------------------------------
  // getTopPerforming
  // -----------------------------------------------------------------------

  /**
   * Retrieve the top-performing copy variants for a given page type.
   *
   * @param pageType  The page type to filter by (e.g. "landing", "email").
   * @param limit     Maximum number of results to return (default 5).
   */
  async getTopPerforming(
    pageType: string,
    limit = 5,
  ): Promise<TopPerformingResult[]> {
    if (!pageType) {
      throw new Error(
        'AnalyticsIntegration.getTopPerforming: pageType is required.',
      );
    }

    const { baseUrl } = this.resolveEndpoint();

    const url = new URL(`${baseUrl}/copy-variants/top`);
    url.searchParams.set('pageType', pageType);
    url.searchParams.set('limit', String(limit));

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: this.buildHeaders(),
    });

    if (!response.ok) {
      throw new Error(
        `AnalyticsIntegration.getTopPerforming failed: ${response.status} ${response.statusText}`,
      );
    }

    const data = (await response.json()) as { results: TopPerformingResult[] };
    return data.results ?? [];
  }

  // -----------------------------------------------------------------------
  // reportConversion
  // -----------------------------------------------------------------------

  /**
   * Report a conversion event tied to a specific piece of copy.
   *
   * @param copyId  Identifier for the copy that drove the conversion.
   * @param event   Name of the conversion event (e.g. "signup", "purchase").
   * @param value   Optional monetary value of the conversion.
   */
  async reportConversion(
    copyId: string,
    event: string,
    value?: number,
  ): Promise<{ success: boolean; eventId: string }> {
    if (!copyId) {
      throw new Error(
        'AnalyticsIntegration.reportConversion: copyId is required.',
      );
    }
    if (!event) {
      throw new Error(
        'AnalyticsIntegration.reportConversion: event is required.',
      );
    }

    const payload: ConversionEvent = {
      copyId,
      event,
      timestamp: new Date().toISOString(),
      value,
    };

    return this.sendEvent(payload);
  }

  // -----------------------------------------------------------------------
  // Private helpers
  // -----------------------------------------------------------------------

  /**
   * Resolve the base URL and path prefix for the configured provider.
   */
  private resolveEndpoint(): { baseUrl: string } {
    if (this.config.baseUrl) {
      return { baseUrl: this.config.baseUrl };
    }

    switch (this.config.provider) {
      case 'mixpanel':
        return { baseUrl: 'https://api.mixpanel.com' };
      case 'ga4':
        return {
          baseUrl: 'https://www.google-analytics.com/mp/collect',
        };
      case 'segment':
        return { baseUrl: 'https://api.segment.io/v1' };
      case 'custom':
        throw new Error(
          'AnalyticsIntegration: baseUrl is required for the "custom" provider.',
        );
      default:
        throw new Error(
          `AnalyticsIntegration: unknown provider "${this.config.provider}".`,
        );
    }
  }

  /**
   * Build request headers including authorization.
   */
  private buildHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...this.config.headers,
    };

    switch (this.config.provider) {
      case 'mixpanel':
        headers['Authorization'] = `Basic ${Buffer.from(this.config.apiKey + ':').toString('base64')}`;
        break;
      case 'segment':
        headers['Authorization'] = `Basic ${Buffer.from(this.config.apiKey + ':').toString('base64')}`;
        break;
      case 'ga4':
        // GA4 uses the api_secret as a query parameter, not a header.
        break;
      default:
        headers['Authorization'] = `Bearer ${this.config.apiKey}`;
        break;
    }

    return headers;
  }

  /**
   * Send a generic event to the analytics provider.
   */
  private async sendEvent(
    payload: Record<string, unknown>,
  ): Promise<{ success: boolean; eventId: string }> {
    const { baseUrl } = this.resolveEndpoint();

    let url = `${baseUrl}/track`;
    if (this.config.provider === 'ga4') {
      url = `${baseUrl}?api_secret=${this.config.apiKey}`;
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: this.buildHeaders(),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(
        `AnalyticsIntegration.sendEvent failed: ${response.status} ${response.statusText}`,
      );
    }

    // Some providers return an ID, others don't. Generate a fallback.
    const data = (await response.json().catch(() => ({}))) as Record<
      string,
      unknown
    >;
    const eventId =
      typeof data.id === 'string'
        ? data.id
        : `evt_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

    return { success: true, eventId };
  }
}
