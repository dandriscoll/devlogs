import type { ConsoleMethod, OriginalConsole } from './types';
import type { DevlogsClient } from './client';
import { getContext } from './context';
import { formatLogDocument, extractSourceLocation } from './formatter';

/**
 * Store original console methods before interception.
 * Used for:
 * 1. Calling the original console so terminal output still works
 * 2. Avoiding infinite loops from internal logging
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
 * Intercept console methods to forward logs to OpenSearch/collector.
 * Original console methods are still called so terminal output works normally.
 * Reads context from AsyncLocalStorage on each call for per-request isolation.
 */
export function interceptConsole(client: DevlogsClient): void {
  METHODS.forEach((method) => {
    console[method] = (...args: unknown[]) => {
      // Capture source location before calling original (preserves stack)
      const source = extractSourceLocation();

      // Always call the original console method
      originalConsole[method](...args);

      // Read context from AsyncLocalStorage (per-request)
      const context = getContext();

      // Format and send
      const doc = formatLogDocument(method, args, context, source);
      client.send(doc);
    };
  });
}

/**
 * Restore original console methods.
 */
export function restoreConsole(): void {
  METHODS.forEach((method) => {
    console[method] = originalConsole[method];
  });
}
