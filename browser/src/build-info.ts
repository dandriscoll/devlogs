/**
 * Build info helper for devlogs browser client.
 *
 * Provides a stable build identifier that applications can use to tag
 * every log entry without requiring git at runtime.
 */

/**
 * Source of the build info.
 */
export type BuildInfoSource = 'file' | 'env' | 'generated';

/**
 * Build information resolved from file, environment, or generated.
 */
export interface BuildInfo {
  /** Unique build identifier (always non-empty). */
  buildId: string;
  /** Git branch name, if available. */
  branch: string | null;
  /** UTC timestamp in format YYYYMMDDTHHMMSSZ. */
  timestampUtc: string;
  /** Source of the build info. */
  source: BuildInfoSource;
  /** File path used for build info, if any. */
  path: string | null;
}

/**
 * Build info file format (JSON).
 */
export interface BuildInfoFile {
  build_id?: string;
  branch?: string;
  timestamp_utc?: string;
  [key: string]: unknown;
}

/**
 * Options for resolving build info.
 */
export interface BuildInfoOptions {
  /** Explicit build info data (e.g., injected at build time). */
  data?: BuildInfoFile;
  /** Environment variable prefix (default: "DEVLOGS_"). */
  envPrefix?: string;
  /** Custom function to get current time (for testing). */
  nowFn?: () => Date;
  /**
   * Environment variables to use (for non-browser environments).
   * In browser, this is typically injected at build time.
   */
  env?: Record<string, string | undefined>;
}

/**
 * Format a Date as compact ISO-like UTC timestamp: YYYYMMDDTHHMMSSZ.
 */
export function formatTimestamp(date: Date): string {
  const pad = (n: number): string => n.toString().padStart(2, '0');
  return (
    date.getUTCFullYear().toString() +
    pad(date.getUTCMonth() + 1) +
    pad(date.getUTCDate()) +
    'T' +
    pad(date.getUTCHours()) +
    pad(date.getUTCMinutes()) +
    pad(date.getUTCSeconds()) +
    'Z'
  );
}

/**
 * Get environment variable value.
 * Uses provided env object, or falls back to globalThis/window if available.
 */
function getEnv(
  name: string,
  env?: Record<string, string | undefined>
): string | undefined {
  if (env) {
    return env[name];
  }
  // Check for Node.js process.env (with typeof check to avoid ReferenceError in browser)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const g = globalThis as any;
  if (typeof g.process !== 'undefined' && g.process?.env) {
    return g.process.env[name];
  }
  return undefined;
}

/**
 * Resolve build information from data, environment, or generate it.
 *
 * Priority order:
 * 1. Environment variable BUILD_ID (if set) takes highest precedence
 * 2. Provided build info data (from file loaded at build time)
 * 3. Environment variables for branch/timestamp
 * 4. Generated values
 *
 * @param options - Configuration options
 * @returns Resolved build info
 *
 * @example
 * ```ts
 * // With build-time injected data
 * import buildData from './.build.json';
 * const bi = resolveBuildInfo({ data: buildData });
 *
 * // With environment variables (Node.js)
 * const bi = resolveBuildInfo();
 *
 * // With custom env (for testing or browser)
 * const bi = resolveBuildInfo({
 *   env: { DEVLOGS_BUILD_ID: 'my-build-123' }
 * });
 * ```
 */
export function resolveBuildInfo(options: BuildInfoOptions = {}): BuildInfo {
  const envPrefix = options.envPrefix ?? 'DEVLOGS_';
  const nowFn = options.nowFn ?? (() => new Date());
  const env = options.env;
  const data = options.data;

  // Environment variable names
  const envBuildId = `${envPrefix}BUILD_ID`;
  const envBranch = `${envPrefix}BRANCH`;
  const envTimestamp = `${envPrefix}BUILD_TIMESTAMP_UTC`;

  // Check for direct BUILD_ID env override (highest precedence)
  const directBuildId = getEnv(envBuildId, env);
  if (directBuildId) {
    const branch = getEnv(envBranch, env) ?? null;
    const timestamp = getEnv(envTimestamp, env) ?? formatTimestamp(nowFn());
    return {
      buildId: directBuildId,
      branch,
      timestampUtc: timestamp,
      source: 'env',
      path: null,
    };
  }

  // Check provided data (from file loaded at build time)
  if (data && typeof data === 'object' && data.build_id) {
    const branch = getEnv(envBranch, env) ?? data.branch ?? null;
    const timestamp =
      getEnv(envTimestamp, env) ?? data.timestamp_utc ?? formatTimestamp(nowFn());
    return {
      buildId: data.build_id,
      branch,
      timestampUtc: timestamp,
      source: 'file',
      path: null, // Path not available in browser context
    };
  }

  // Check if env provides branch and/or timestamp
  const envBranchValue = getEnv(envBranch, env);
  const envTimestampValue = getEnv(envTimestamp, env);

  // Determine branch
  const branch = envBranchValue ?? null;

  // Determine timestamp
  const timestamp = envTimestampValue ?? formatTimestamp(nowFn());

  // Generate build_id
  const branchForId = branch ?? 'unknown';
  const buildId = `${branchForId}-${timestamp}`;

  // Determine source
  const source: BuildInfoSource =
    envBranchValue || envTimestampValue ? 'env' : 'generated';

  return {
    buildId,
    branch,
    timestampUtc: timestamp,
    source,
    path: null,
  };
}

/**
 * Convenience function that returns only the build_id string.
 *
 * @param options - Configuration options (same as resolveBuildInfo)
 * @returns Non-empty build identifier string
 */
export function resolveBuildId(options: BuildInfoOptions = {}): string {
  return resolveBuildInfo(options).buildId;
}

/**
 * Create build info data object for writing to .build.json during build.
 *
 * This is a utility for build scripts to generate the build info file.
 *
 * @param options - Configuration options
 * @returns Build info data object suitable for JSON.stringify
 *
 * @example
 * ```ts
 * // In a build script (Node.js)
 * import { createBuildInfoData } from 'devlogs-browser/build-info';
 * import fs from 'fs';
 *
 * const data = createBuildInfoData({ branch: process.env.GITHUB_REF_NAME });
 * fs.writeFileSync('.build.json', JSON.stringify(data, null, 2));
 * ```
 */
export function createBuildInfoData(
  options: {
    branch?: string;
    nowFn?: () => Date;
  } = {}
): BuildInfoFile {
  const nowFn = options.nowFn ?? (() => new Date());
  const branch = options.branch ?? null;
  const timestamp = formatTimestamp(nowFn());
  const branchForId = branch ?? 'unknown';
  const buildId = `${branchForId}-${timestamp}`;

  return {
    build_id: buildId,
    branch: branch ?? undefined,
    timestamp_utc: timestamp,
  };
}
