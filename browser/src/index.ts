import type { DevlogsOptions } from './types';
import { parseDevlogsUrl } from './url-parser';
import { DevlogsOpenSearchClient } from './client';
import {
  interceptConsole,
  restoreConsole,
  setContext,
  setArea,
  setOperationId,
  setFeatures,
  withOperation,
  originalConsole,
} from './interceptor';

let initialized = false;
let client: DevlogsOpenSearchClient | null = null;

/**
 * Initialize the devlogs browser client.
 *
 * This intercepts console.log/warn/error/debug/info and forwards
 * all log messages to the OpenSearch index.
 *
 * @example
 * ```js
 * devlogs.init({
 *   url: 'http://admin:admin@localhost:9200',
 *   area: 'frontend',
 *   loggerName: 'my-app'
 * });
 *
 * console.log('App started'); // Forwarded to index
 * ```
 */
export function init(options: DevlogsOptions): void {
  if (initialized) {
    originalConsole.warn('[devlogs] Already initialized');
    return;
  }

  const config = parseDevlogsUrl(options.url, options.index);
  client = new DevlogsOpenSearchClient(config);

  setContext({
    area: options.area || null,
    operationId: options.operationId || null,
    loggerName: options.loggerName || 'browser',
    pathname: typeof window !== 'undefined' ? window.location.pathname : '/',
    features: {},
  });

  interceptConsole(client);
  initialized = true;
}

/**
 * Disable devlogs and restore original console methods.
 */
export function destroy(): void {
  if (!initialized) {
    return;
  }

  restoreConsole();
  client = null;
  initialized = false;
}

/**
 * Check if devlogs is currently initialized
 */
export function isInitialized(): boolean {
  return initialized;
}

// Re-export context utilities
export { setArea, setOperationId, setFeatures, withOperation };

// Re-export types for TypeScript users
export type { DevlogsOptions, LogContext, LogDocument } from './types';

// Re-export build info utilities
export {
  resolveBuildInfo,
  resolveBuildId,
  createBuildInfoData,
  formatTimestamp,
} from './build-info';
export type {
  BuildInfo,
  BuildInfoSource,
  BuildInfoFile,
  BuildInfoOptions,
} from './build-info';
