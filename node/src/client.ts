import http from 'node:http';
import https from 'node:https';
import type { DevlogsConfig, LogDocument } from './types';
import { CircuitBreaker } from './circuit-breaker';

/**
 * Dual-mode HTTP client for sending log documents.
 *
 * - OpenSearch mode: POST to /{index}/_doc with Basic auth
 * - Collector mode: POST to / with optional Bearer token
 * - Fire-and-forget: does not await response
 * - Circuit breaker: stops sending on failures, auto-recovers
 */
export class DevlogsClient {
  private readonly config: DevlogsConfig;
  private readonly cb: CircuitBreaker;

  constructor(config: DevlogsConfig, cb?: CircuitBreaker) {
    this.config = config;
    this.cb = cb ?? new CircuitBreaker();
  }

  /**
   * Send a log document. Fire-and-forget - does not block.
   */
  send(doc: LogDocument): void {
    if (this.cb.shouldSkip()) return;

    const body = JSON.stringify(doc);
    const transport = this.config.scheme === 'https' ? https : http;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body).toString(),
    };

    let path: string;

    if (this.config.mode === 'opensearch') {
      path = `/${this.config.index}/_doc`;
      const credentials = `${this.config.user}:${this.config.password}`;
      headers['Authorization'] = `Basic ${Buffer.from(credentials).toString('base64')}`;
    } else {
      path = '/';
      if (this.config.token) {
        headers['Authorization'] = `Bearer ${this.config.token}`;
      }
    }

    const req = transport.request(
      {
        hostname: this.config.host,
        port: this.config.port,
        path,
        method: 'POST',
        headers,
      },
      (res) => {
        // Consume response to free socket
        res.resume();

        const status = res.statusCode ?? 0;
        if (status >= 200 && status < 300) {
          this.cb.recordSuccess();
        } else {
          this.cb.recordFailure(
            new Error(`HTTP ${status} from ${this.config.mode}`)
          );
        }
      }
    );

    req.on('error', (err) => {
      this.cb.recordFailure(err);
    });

    req.end(body);
  }
}
