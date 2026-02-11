import type { DevlogsOptions } from './types';
import { parseDevlogsUrl } from './url-parser';
import { loadEnvConfig } from './config';
import { DevlogsClient } from './client';
import {
  interceptConsole,
  restoreConsole,
  originalConsole,
} from './interceptor';
import {
  setDefaultContext,
  setArea,
  setOperationId,
  setFields,
  withOperation,
  withContext,
  resetContext,
} from './context';

let initialized = false;
let client: DevlogsClient | null = null;

/**
 * Initialize the devlogs node client.
 *
 * Auto-loads configuration from DEVLOGS_* environment variables and .env.devlogs
 * files if options are not explicitly provided.
 *
 * @example
 * ```js
 * // Auto-load from environment
 * devlogs.init();
 *
 * // Or provide explicit options
 * devlogs.init({
 *   url: 'http://admin:admin@localhost:9200',
 *   application: 'my-api',
 *   component: 'server',
 * });
 * ```
 */
export function init(options?: DevlogsOptions): void {
  if (initialized) {
    originalConsole.warn('[devlogs] Already initialized');
    return;
  }

  // Merge explicit options with env config
  const envConfig = loadEnvConfig();
  const url = options?.url ?? envConfig.url;
  const application = options?.application ?? envConfig.application;
  const component = options?.component ?? envConfig.component;

  if (!url) {
    originalConsole.warn(
      '[devlogs] No URL configured. Set DEVLOGS_URL or pass url option.'
    );
    return;
  }
  if (!application) {
    originalConsole.warn(
      '[devlogs] No application configured. Set DEVLOGS_APPLICATION or pass application option.'
    );
    return;
  }
  if (!component) {
    originalConsole.warn(
      '[devlogs] No component configured. Set DEVLOGS_COMPONENT or pass component option.'
    );
    return;
  }

  const config = parseDevlogsUrl(url, options?.index ?? envConfig.index);
  client = new DevlogsClient(config);

  setDefaultContext({
    application,
    component,
    area: options?.area ?? envConfig.area ?? null,
    operationId: options?.operationId ?? null,
    environment: options?.environment ?? envConfig.environment ?? null,
    version: options?.version ?? envConfig.version ?? null,
    fields: {},
  });

  interceptConsole(client);
  initialized = true;
}

/**
 * Disable devlogs and restore original console methods.
 */
export function destroy(): void {
  if (!initialized) return;

  restoreConsole();
  resetContext();
  client = null;
  initialized = false;
}

/**
 * Check if devlogs is currently initialized.
 */
export function isInitialized(): boolean {
  return initialized;
}

// Re-export context utilities
export { setArea, setOperationId, setFields, withOperation, withContext };

// Re-export types
export type {
  DevlogsOptions,
  DevlogsConfig,
  OpenSearchConfig,
  CollectorConfig,
  LogContext,
  LogDocument,
  LogSource,
  LogProcess,
  DevlogsMode,
} from './types';

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
