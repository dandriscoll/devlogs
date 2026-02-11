/**
 * Build info helper for devlogs node client.
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
  /** Environment variables to use. Defaults to process.env. */
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
 */
function getEnv(
  name: string,
  env?: Record<string, string | undefined>
): string | undefined {
  if (env) return env[name];
  return process.env[name];
}

/**
 * Resolve build information from data, environment, or generate it.
 *
 * Priority order:
 * 1. Environment variable BUILD_ID (highest precedence)
 * 2. Provided build info data (from file)
 * 3. Environment variables for branch/timestamp
 * 4. Generated values
 */
export function resolveBuildInfo(options: BuildInfoOptions = {}): BuildInfo {
  const envPrefix = options.envPrefix ?? 'DEVLOGS_';
  const nowFn = options.nowFn ?? (() => new Date());
  const env = options.env;
  const data = options.data;

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
      path: null,
    };
  }

  // Check if env provides branch and/or timestamp
  const envBranchValue = getEnv(envBranch, env);
  const envTimestampValue = getEnv(envTimestamp, env);

  const branch = envBranchValue ?? null;
  const timestamp = envTimestampValue ?? formatTimestamp(nowFn());
  const branchForId = branch ?? 'unknown';
  const buildId = `${branchForId}-${timestamp}`;

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
 */
export function resolveBuildId(options: BuildInfoOptions = {}): string {
  return resolveBuildInfo(options).buildId;
}

/**
 * Create build info data object for writing to .build.json during build.
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
