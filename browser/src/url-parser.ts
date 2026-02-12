import type { DevlogsConfig, OpenSearchConfig, CollectorConfig } from './types';

/**
 * Parse a devlogs URL and auto-detect mode.
 *
 * Detection logic:
 * - user:pass@ in URL → OpenSearch direct mode
 * - token@ (no password) or no credentials → Collector mode
 *
 * Supports schemes: http://, https://, opensearch://, opensearchs://
 */
export function parseDevlogsUrl(url: string, index?: string): DevlogsConfig {
  // Normalize opensearch(s):// to http(s)://
  let normalizedUrl = url;
  let forceOpenSearch = false;

  if (url.startsWith('opensearchs://')) {
    normalizedUrl = 'https://' + url.slice('opensearchs://'.length);
    forceOpenSearch = true;
  } else if (url.startsWith('opensearch://')) {
    normalizedUrl = 'http://' + url.slice('opensearch://'.length);
    forceOpenSearch = true;
  }

  const parsed = new URL(normalizedUrl);
  const scheme = parsed.protocol.replace(':', '') as 'http' | 'https';
  const host = parsed.hostname || 'localhost';
  const port = parsed.port
    ? parseInt(parsed.port, 10)
    : scheme === 'https'
      ? 443
      : 9200;

  // Extract index from path if present (e.g., /devlogs-myapp)
  const pathIndex = parsed.pathname && parsed.pathname !== '/'
    ? parsed.pathname.slice(1).split('/')[0]
    : undefined;

  const resolvedIndex = index || pathIndex || 'devlogs-0001';

  // Determine mode:
  // 1. opensearch(s):// scheme → always OpenSearch
  // 2. Both user AND password → OpenSearch
  // 3. User only (no password) → Collector with token
  // 4. No credentials → Collector
  if (forceOpenSearch || (parsed.username && parsed.password)) {
    return {
      mode: 'opensearch',
      scheme,
      host,
      port,
      user: decodeURIComponent(parsed.username || 'admin'),
      password: decodeURIComponent(parsed.password || 'admin'),
      index: resolvedIndex,
    } satisfies OpenSearchConfig;
  }

  // Collector mode: username-only is a token
  const token = parsed.username ? decodeURIComponent(parsed.username) : null;

  return {
    mode: 'collector',
    scheme,
    host,
    port,
    token,
    index: resolvedIndex,
  } satisfies CollectorConfig;
}
