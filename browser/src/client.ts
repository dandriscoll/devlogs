import type { DevlogsConfig, LogDocument } from './types';
import { originalConsole } from './interceptor';

/**
 * Lightweight OpenSearch client for browser environments.
 *
 * Features:
 * - Uses native fetch API (no dependencies)
 * - Circuit breaker pattern: shows single error on connection failure
 * - Fire-and-forget logging (non-blocking)
 */
export class DevlogsOpenSearchClient {
  private readonly baseUrl: string;
  private readonly authHeader: string;
  private readonly indexName: string;
  private circuitOpen = false;
  private errorShown = false;

  constructor(config: DevlogsConfig) {
    this.baseUrl = `${config.scheme}://${config.host}:${config.port}`;
    this.authHeader = `Basic ${btoa(`${config.user}:${config.password}`)}`;
    this.indexName = config.index;
  }

  /**
   * Index a log document. Fire-and-forget - does not await response.
   */
  index(doc: LogDocument): void {
    if (this.circuitOpen) {
      return;
    }

    fetch(`${this.baseUrl}/${this.indexName}/_doc`, {
      method: 'POST',
      headers: {
        'Authorization': this.authHeader,
        'Content-Type': 'application/json',
      },
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
