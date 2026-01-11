import type { LogContext, LogDocument, ConsoleMethod } from './types';

/**
 * Python logging level numbers for compatibility
 */
const LEVEL_MAP: Record<ConsoleMethod, number> = {
  debug: 10,
  info: 20,
  log: 20,  // Treat console.log as INFO level
  warn: 30,
  error: 40,
};

/**
 * Normalize console method name to standard log level
 */
function normalizeLevel(method: ConsoleMethod): string {
  if (method === 'warn') return 'warning';
  if (method === 'log') return 'info';
  return method;
}

/**
 * Format console arguments into a single message string
 */
function formatMessage(args: unknown[]): string {
  return args
    .map((arg) => {
      if (typeof arg === 'string') {
        return arg;
      }
      if (arg instanceof Error) {
        return `${arg.name}: ${arg.message}`;
      }
      try {
        return JSON.stringify(arg);
      } catch {
        return String(arg);
      }
    })
    .join(' ');
}

/**
 * Extract features from console arguments if an object is provided
 */
function extractFeatures(
  args: unknown[],
  contextFeatures: Record<string, unknown>
): Record<string, unknown> {
  const features: Record<string, unknown> = {
    userAgent: navigator.userAgent,
    ...contextFeatures,
  };

  // If last argument is a plain object, merge it as features
  const lastArg = args[args.length - 1];
  if (
    lastArg &&
    typeof lastArg === 'object' &&
    !Array.isArray(lastArg) &&
    !(lastArg instanceof Error)
  ) {
    Object.assign(features, lastArg);
  }

  return features;
}

/**
 * Format a log entry into the devlogs document schema
 */
export function formatLogDocument(
  method: ConsoleMethod,
  args: unknown[],
  context: LogContext
): LogDocument {
  return {
    doc_type: 'log_entry',
    timestamp: new Date().toISOString(),
    level: normalizeLevel(method),
    levelno: LEVEL_MAP[method],
    logger_name: context.loggerName,
    message: formatMessage(args),
    pathname: context.pathname,
    lineno: null,
    funcName: null,
    area: context.area,
    operation_id: context.operationId,
    features: extractFeatures(args, context.features),
  };
}
