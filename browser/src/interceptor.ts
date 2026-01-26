import type { ConsoleMethod, LogContext, OriginalConsole } from './types';
import type { DevlogsOpenSearchClient } from './client';
import { formatLogDocument } from './formatter';

/**
 * Store original console methods before interception.
 * These are used for:
 * 1. Calling the original console so browser devtools still work
 * 2. Error reporting from the client without causing infinite loops
 */
export const originalConsole: OriginalConsole = {
  log: console.log.bind(console),
  warn: console.warn.bind(console),
  error: console.error.bind(console),
  debug: console.debug.bind(console),
  info: console.info.bind(console),
};

const METHODS: readonly ConsoleMethod[] = ['log', 'warn', 'error', 'debug', 'info'];

/**
 * Current logging context - shared across all console calls
 */
let currentContext: LogContext = {
  application: 'unknown',
  component: 'browser',
  area: null,
  operationId: null,
  pathname: typeof window !== 'undefined' ? window.location.pathname : '/',
  environment: null,
  version: null,
  fields: {},
};

/**
 * Get the current logging context
 */
export function getContext(): LogContext {
  return { ...currentContext };
}

/**
 * Update the logging context
 */
export function setContext(updates: Partial<LogContext>): void {
  currentContext = { ...currentContext, ...updates };
}

/**
 * Set the application area
 */
export function setArea(area: string | null): void {
  currentContext.area = area;
}

/**
 * Set the operation ID for correlation
 */
export function setOperationId(operationId: string | null): void {
  currentContext.operationId = operationId;
}

/**
 * Set custom fields to include in all logs
 */
export function setFields(fields: Record<string, unknown>): void {
  currentContext.fields = fields;
}

/**
 * @deprecated Use setFields instead
 */
export function setFeatures(features: Record<string, unknown>): void {
  setFields(features);
}

/**
 * Execute a function with a temporary operation ID
 */
export function withOperation<T>(operationId: string, fn: () => T): T {
  const previousId = currentContext.operationId;
  currentContext.operationId = operationId;
  try {
    return fn();
  } finally {
    currentContext.operationId = previousId;
  }
}

/**
 * Intercept console methods to forward logs to the index.
 * Original console methods are still called so devtools work normally.
 */
export function interceptConsole(client: DevlogsOpenSearchClient): void {
  METHODS.forEach((method) => {
    console[method] = (...args: unknown[]) => {
      // Always call the original console method first
      originalConsole[method](...args);

      // Format and send to index
      const doc = formatLogDocument(method, args, getContext());
      client.index(doc);
    };
  });
}

/**
 * Restore original console methods
 */
export function restoreConsole(): void {
  METHODS.forEach((method) => {
    console[method] = originalConsole[method];
  });
}
