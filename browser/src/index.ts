import type { DevlogsOptions } from './types';
import { parseDevlogsUrl } from './url-parser';
import { DevlogsClient } from './client';
import {
  interceptConsole,
  restoreConsole,
  installGlobalHandlers as installGlobalHandlersImpl,
  removeGlobalHandlers,
  setContext,
  setArea,
  setOperationId,
  setFields,
  setFeatures,
  withOperation,
  originalConsole,
} from './interceptor';

let initialized = false;
let client: DevlogsClient | null = null;

/**
 * Initialize the devlogs browser client (v2.0).
 *
 * This intercepts console.log/warn/error/debug/info and forwards
 * all log messages to the OpenSearch index.
 *
 * @example
 * ```js
 * devlogs.init({
 *   url: 'http://admin:admin@localhost:9200',
 *   application: 'my-frontend',
 *   component: 'dashboard',
 *   area: 'ui',
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
  client = new DevlogsClient(config);

  setContext({
    application: options.application,
    component: options.component,
    area: options.area || null,
    operationId: options.operationId || null,
    pathname: typeof window !== 'undefined' ? window.location.pathname : '/',
    environment: options.environment || null,
    version: options.version || null,
    fields: {},
  });

  interceptConsole(client);
  initialized = true;
}

/**
 * Install global handlers for uncaught errors and unhandled promise rejections.
 * Must be called after init(). These capture errors that never pass through
 * console.error(), such as uncaught exceptions and unhandled promise rejections.
 *
 * @example
 * ```js
 * devlogs.init({ url: '...', application: 'my-app', component: 'ui' });
 * devlogs.installGlobalHandlers();
 * // Now uncaught errors and unhandled rejections are captured automatically
 * ```
 */
export function installGlobalHandlers(): void {
  if (!initialized || !client) {
    originalConsole.warn('[devlogs] Must call init() before installGlobalHandlers()');
    return;
  }
  installGlobalHandlersImpl(client);
}

/**
 * Disable devlogs and restore original console methods.
 */
export function destroy(): void {
  if (!initialized) {
    return;
  }

  removeGlobalHandlers();
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
export { setArea, setOperationId, setFields, setFeatures, withOperation };

// Note: installGlobalHandlers is exported directly above as a named function

// Re-export types for TypeScript users
export type { DevlogsOptions, LogContext, LogDocument, LogSource, LogProcess } from './types';

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
