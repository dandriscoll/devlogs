/**
 * Mode of operation: direct OpenSearch or collector endpoint.
 */
export type DevlogsMode = 'opensearch' | 'collector';

/**
 * Options for initializing the devlogs node client.
 * All fields are optional - values are loaded from DEVLOGS_* env vars if not provided.
 */
export interface DevlogsOptions {
  /** URL in format: http://user:pass@host:port (OpenSearch) or http://token@host:port (collector) */
  url?: string;
  /** Index name (default: devlogs-0001) */
  index?: string;
  /** Application name */
  application?: string;
  /** Component name */
  component?: string;
  /** Application area/subsystem identifier */
  area?: string;
  /** Operation ID for log correlation */
  operationId?: string;
  /** Environment (e.g., 'development', 'production') */
  environment?: string;
  /** Application version */
  version?: string;
}

/**
 * Parsed configuration for OpenSearch mode.
 */
export interface OpenSearchConfig {
  mode: 'opensearch';
  scheme: 'http' | 'https';
  host: string;
  port: number;
  user: string;
  password: string;
  index: string;
}

/**
 * Parsed configuration for collector mode.
 */
export interface CollectorConfig {
  mode: 'collector';
  scheme: 'http' | 'https';
  host: string;
  port: number;
  token: string | null;
  index: string;
}

/**
 * Union of both config modes.
 */
export type DevlogsConfig = OpenSearchConfig | CollectorConfig;

/**
 * Current logging context (per-request via AsyncLocalStorage).
 */
export interface LogContext {
  application: string;
  component: string;
  area: string | null;
  operationId: string | null;
  environment: string | null;
  version: string | null;
  fields: Record<string, unknown>;
}

/**
 * Source location info in log document (v2.0).
 */
export interface LogSource {
  logger: string;
  pathname: string | null;
  lineno: number | null;
  funcName: string | null;
}

/**
 * Process info in log document (v2.0).
 */
export interface LogProcess {
  id: number | null;
  thread: number | null;
}

/**
 * Log document matching the devlogs v2.0 schema.
 */
export interface LogDocument {
  doc_type: 'log_entry';
  application: string;
  component: string;
  timestamp: string;
  message: string;
  level: string;
  area: string | null;
  environment?: string | null;
  version?: string | null;
  operation_id: string | null;
  fields?: Record<string, unknown>;
  source: LogSource;
  process: LogProcess;
}

/**
 * Console method names that we intercept.
 */
export type ConsoleMethod = 'log' | 'warn' | 'error' | 'debug' | 'info';

/**
 * Mapping of console methods to their original implementations.
 */
export type OriginalConsole = {
  [K in ConsoleMethod]: (...args: unknown[]) => void;
};
