import type { LogContext, LogDocument, ConsoleMethod } from './types';

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
 * Extract fields from console arguments if an object is provided
 */
function extractFields(
  args: unknown[],
  contextFields: Record<string, unknown>
): Record<string, unknown> {
  const fields: Record<string, unknown> = {
    userAgent: navigator.userAgent,
    ...contextFields,
  };

  // If last argument is a plain object, merge it as fields
  const lastArg = args[args.length - 1];
  if (
    lastArg &&
    typeof lastArg === 'object' &&
    !Array.isArray(lastArg) &&
    !(lastArg instanceof Error)
  ) {
    Object.assign(fields, lastArg);
  }

  return fields;
}

/**
 * Format a log entry into the devlogs v2.0 document schema
 */
export function formatLogDocument(
  method: ConsoleMethod,
  args: unknown[],
  context: LogContext
): LogDocument {
  const fields = extractFields(args, context.fields);

  const doc: LogDocument = {
    doc_type: 'log_entry',
    // Required fields
    application: context.application,
    component: context.component,
    timestamp: new Date().toISOString(),
    // Top-level log fields
    message: formatMessage(args),
    level: normalizeLevel(method),
    area: context.area,
    // Optional metadata
    operation_id: context.operationId,
    // Source info
    source: {
      logger: 'browser',
      pathname: context.pathname,
      lineno: null,
      funcName: null,
    },
    // Process info (not applicable in browser)
    process: {
      id: null,
      thread: null,
    },
  };

  // Add optional fields only if set
  if (context.environment) {
    doc.environment = context.environment;
  }
  if (context.version) {
    doc.version = context.version;
  }
  if (Object.keys(fields).length > 0) {
    doc.fields = fields;
  }

  return doc;
}
