import { AsyncLocalStorage } from 'node:async_hooks';
import type { LogContext } from './types';

/**
 * AsyncLocalStorage instance for per-request context isolation.
 * Each async context (e.g., HTTP request handler) gets its own LogContext.
 */
const storage = new AsyncLocalStorage<LogContext>();

/**
 * Default context used when no async context is active.
 */
let defaultContext: LogContext = {
  application: 'unknown',
  component: 'node',
  area: null,
  operationId: null,
  environment: null,
  version: null,
  fields: {},
};

/**
 * Set the default context values (called during init).
 */
export function setDefaultContext(ctx: Partial<LogContext>): void {
  defaultContext = { ...defaultContext, ...ctx };
}

/**
 * Get the current logging context.
 * Returns the AsyncLocalStorage context if inside withContext/withOperation,
 * otherwise returns the default (module-level) context.
 */
export function getContext(): LogContext {
  return storage.getStore() ?? { ...defaultContext };
}

/**
 * Set the application area in the current context.
 */
export function setArea(area: string | null): void {
  const store = storage.getStore();
  if (store) {
    store.area = area;
  } else {
    defaultContext.area = area;
  }
}

/**
 * Set the operation ID in the current context.
 */
export function setOperationId(operationId: string | null): void {
  const store = storage.getStore();
  if (store) {
    store.operationId = operationId;
  } else {
    defaultContext.operationId = operationId;
  }
}

/**
 * Set custom fields in the current context.
 */
export function setFields(fields: Record<string, unknown>): void {
  const store = storage.getStore();
  if (store) {
    store.fields = { ...store.fields, ...fields };
  } else {
    defaultContext.fields = { ...defaultContext.fields, ...fields };
  }
}

/**
 * Run a function with a temporary operation ID in an isolated async context.
 * The operation ID is automatically scoped to the callback and its async children.
 */
export function withOperation<T>(operationId: string, fn: () => T): T {
  const parent = getContext();
  const childCtx: LogContext = {
    ...parent,
    operationId,
    fields: { ...parent.fields },
  };
  return storage.run(childCtx, fn);
}

/**
 * Run a function with a fully isolated async context.
 * Changes made inside the callback don't affect the parent context.
 */
export function withContext<T>(overrides: Partial<LogContext>, fn: () => T): T {
  const parent = getContext();
  const childCtx: LogContext = {
    ...parent,
    ...overrides,
    fields: { ...parent.fields, ...overrides.fields },
  };
  return storage.run(childCtx, fn);
}

/**
 * Reset the default context (for testing/destroy).
 */
export function resetContext(): void {
  defaultContext = {
    application: 'unknown',
    component: 'node',
    area: null,
    operationId: null,
    environment: null,
    version: null,
    fields: {},
  };
}
