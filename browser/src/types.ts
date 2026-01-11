/**
 * Configuration parsed from the DEVLOGS URL
 */
export interface DevlogsConfig {
  scheme: 'http' | 'https';
  host: string;
  port: number;
  user: string;
  password: string;
  index: string;
}

/**
 * Options for initializing the devlogs client
 */
export interface DevlogsOptions {
  /** OpenSearch URL in format: http://user:pass@host:port */
  url: string;
  /** Index name (default: devlogs-0001) */
  index?: string;
  /** Application area/subsystem identifier */
  area?: string;
  /** Operation ID for log correlation */
  operationId?: string;
  /** Logger name (default: browser) */
  loggerName?: string;
}

/**
 * Current logging context
 */
export interface LogContext {
  area: string | null;
  operationId: string | null;
  loggerName: string;
  pathname: string;
  features: Record<string, unknown>;
}

/**
 * Log document matching the devlogs schema
 */
export interface LogDocument {
  doc_type: 'log_entry';
  timestamp: string;
  level: string;
  levelno: number;
  logger_name: string;
  message: string;
  pathname: string;
  lineno: number | null;
  funcName: string | null;
  area: string | null;
  operation_id: string | null;
  features: Record<string, unknown>;
}

/**
 * Console method names that we intercept
 */
export type ConsoleMethod = 'log' | 'warn' | 'error' | 'debug' | 'info';

/**
 * Mapping of console methods to their original implementations
 */
export type OriginalConsole = {
  [K in ConsoleMethod]: (...args: unknown[]) => void;
};
