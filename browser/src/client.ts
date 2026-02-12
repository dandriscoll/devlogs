import type { DevlogsConfig, LogDocument } from './types';
import { originalConsole } from './interceptor';

/**
 * Lightweight log client for browser environments.
 *
 * Features:
 * - Uses native fetch API (no dependencies)
 * - Supports both OpenSearch and collector modes
 * - Circuit breaker pattern: shows single error on connection failure
 * - Fire-and-forget logging (non-blocking)
 */
export class DevlogsClient {
  private readonly url: string;
  private readonly authHeader: string | null;
  private circuitOpen = false;
  private errorShown = false;

  constructor(config: DevlogsConfig) {
    const baseUrl = `${config.scheme}://${config.host}:${config.port}`;

    if (config.mode === 'opensearch') {
      this.url = `${baseUrl}/${config.index}/_doc`;
      this.authHeader = `Basic ${btoa(`${config.user}:${config.password}`)}`;
    } else {
      this.url = `${baseUrl}/`;
      this.authHeader = config.token ? `Bearer ${config.token}` : null;
    }
  }

  /**
   * Index a log document. Fire-and-forget - does not await response.
   */
  index(doc: LogDocument): void {
    if (this.circuitOpen) {
      return;
    }

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (this.authHeader) {
      headers['Authorization'] = this.authHeader;
    }

    fetch(this.url, {
      method: 'POST',
      headers,
      body: JSON.stringify(doc),
    }).catch((error) => {
      this.handleConnectionError(error);
    });
  }

  private handleConnectionError(error: unknown): void {
    this.circuitOpen = true;

    if (!this.errorShown) {
      this.errorShown = true;
      originalConsole.error('[devlogs] Unable to connect to index:', error);
    }
  }
}
