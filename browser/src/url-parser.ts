import type { DevlogsConfig } from './types';

/**
 * Parse a DEVLOGS URL into configuration components.
 *
 * Supports format: http://user:pass@host:port or https://user:pass@host:port
 *
 * Defaults:
 * - scheme: http
 * - host: localhost
 * - port: 9200 for http, 443 for https
 * - user: admin
 * - password: admin
 * - index: devlogs-0001
 */
export function parseDevlogsUrl(url: string, index?: string): DevlogsConfig {
  const parsed = new URL(url);
  const scheme = parsed.protocol.replace(':', '') as 'http' | 'https';

  return {
    scheme,
    host: parsed.hostname || 'localhost',
    port: parsed.port
      ? parseInt(parsed.port, 10)
      : (scheme === 'https' ? 443 : 9200),
    user: parsed.username || 'admin',
    password: parsed.password || 'admin',
    index: index || 'devlogs-0001',
  };
}
