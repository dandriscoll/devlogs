import type { LogContext, LogDocument, LogSource, ConsoleMethod } from './types';

/**
 * Normalize console method name to standard log level.
 */
function normalizeLevel(method: ConsoleMethod): string {
  if (method === 'warn') return 'warning';
  if (method === 'log') return 'info';
  return method;
}

/**
 * Format console arguments into a single message string.
 */
function formatMessage(args: unknown[]): string {
  return args
    .map((arg) => {
      if (typeof arg === 'string') return arg;
      if (arg instanceof Error) return `${arg.name}: ${arg.message}`;
      try {
        return JSON.stringify(arg);
      } catch {
        return String(arg);
      }
    })
    .join(' ');
}

/**
 * Extract source location from an Error stack trace.
 * Walks the stack to find the first frame outside of devlogs internals.
 */
export function extractSourceLocation(): LogSource {
  const base: LogSource = {
    logger: 'node',
    pathname: null,
    lineno: null,
    funcName: null,
  };

  const err = new Error();
  const stack = err.stack;
  if (!stack) return base;

  const lines = stack.split('\n');

  // Skip frames inside devlogs (interceptor, formatter, index)
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i].trim();

    // Skip internal devlogs package frames
    if (
      line.includes('devlogs.cjs') ||
      line.includes('devlogs.esm') ||
      line.includes('node_modules/devlogs-node') ||
      line.includes('/node/dist/') ||
      line.includes('/node/src/interceptor.') ||
      line.includes('/node/src/formatter.') ||
      line.includes('/node/src/index.')
    ) {
      continue;
    }

    // Parse V8 stack frame: "at funcName (file:line:col)" or "at file:line:col"
    const withFunc = line.match(/at\s+(.+?)\s+\((.+?):(\d+):\d+\)/);
    if (withFunc) {
      return {
        logger: 'node',
        pathname: withFunc[2],
        lineno: parseInt(withFunc[3], 10),
        funcName: withFunc[1],
      };
    }

    const noFunc = line.match(/at\s+(.+?):(\d+):\d+/);
    if (noFunc) {
      return {
        logger: 'node',
        pathname: noFunc[1],
        lineno: parseInt(noFunc[2], 10),
        funcName: null,
      };
    }
  }

  return base;
}

/**
 * Extract fields from console arguments if an object is provided.
 */
function extractFields(
  args: unknown[],
  contextFields: Record<string, unknown>
): Record<string, unknown> {
  const fields: Record<string, unknown> = { ...contextFields };

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
 * Format a log entry into the devlogs v2.0 document schema.
 */
export function formatLogDocument(
  method: ConsoleMethod,
  args: unknown[],
  context: LogContext,
  source?: LogSource
): LogDocument {
  const fields = extractFields(args, context.fields);
  const resolvedSource = source ?? extractSourceLocation();

  const doc: LogDocument = {
    doc_type: 'log_entry',
    application: context.application,
    component: context.component,
    timestamp: new Date().toISOString(),
    message: formatMessage(args),
    level: normalizeLevel(method),
    area: context.area,
    operation_id: context.operationId,
    source: resolvedSource,
    process: {
      id: process.pid,
      thread: null,
    },
  };

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
