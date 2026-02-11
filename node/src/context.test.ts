import { describe, it, expect, beforeEach } from 'vitest';
import {
  getContext,
  setArea,
  setOperationId,
  setFields,
  withOperation,
  withContext,
  setDefaultContext,
  resetContext,
} from './context';

describe('context', () => {
  beforeEach(() => {
    resetContext();
  });

  it('returns default context', () => {
    const ctx = getContext();
    expect(ctx.application).toBe('unknown');
    expect(ctx.component).toBe('node');
    expect(ctx.area).toBeNull();
    expect(ctx.operationId).toBeNull();
  });

  it('updates default context with setDefaultContext', () => {
    setDefaultContext({ application: 'my-app', component: 'api' });
    const ctx = getContext();
    expect(ctx.application).toBe('my-app');
    expect(ctx.component).toBe('api');
  });

  it('setArea updates default context outside async scope', () => {
    setArea('auth');
    expect(getContext().area).toBe('auth');
  });

  it('setOperationId updates default context outside async scope', () => {
    setOperationId('op-1');
    expect(getContext().operationId).toBe('op-1');
  });

  it('setFields merges into default context', () => {
    setFields({ userId: 42 });
    setFields({ requestId: 'abc' });
    const ctx = getContext();
    expect(ctx.fields).toEqual({ userId: 42, requestId: 'abc' });
  });

  describe('withOperation', () => {
    it('scopes operation ID to callback', () => {
      setDefaultContext({ application: 'app', component: 'svc' });

      let innerOpId: string | null = null;
      withOperation('req-123', () => {
        innerOpId = getContext().operationId;
      });

      expect(innerOpId).toBe('req-123');
      expect(getContext().operationId).toBeNull();
    });

    it('returns the callback result', () => {
      const result = withOperation('op', () => 42);
      expect(result).toBe(42);
    });

    it('supports async callbacks', async () => {
      let innerOpId: string | null = null;

      await withOperation('async-op', async () => {
        await new Promise((r) => setTimeout(r, 10));
        innerOpId = getContext().operationId;
      });

      expect(innerOpId).toBe('async-op');
    });

    it('isolates concurrent operations', async () => {
      const results: string[] = [];

      await Promise.all([
        withOperation('op-a', async () => {
          await new Promise((r) => setTimeout(r, 20));
          results.push(`a:${getContext().operationId}`);
        }),
        withOperation('op-b', async () => {
          await new Promise((r) => setTimeout(r, 10));
          results.push(`b:${getContext().operationId}`);
        }),
      ]);

      expect(results).toContain('a:op-a');
      expect(results).toContain('b:op-b');
    });
  });

  describe('withContext', () => {
    it('scopes full context overrides to callback', () => {
      setDefaultContext({ application: 'app', component: 'svc' });

      let innerCtx: ReturnType<typeof getContext> | null = null;
      withContext({ area: 'billing', operationId: 'pay-1' }, () => {
        innerCtx = getContext();
      });

      expect(innerCtx!.area).toBe('billing');
      expect(innerCtx!.operationId).toBe('pay-1');
      expect(innerCtx!.application).toBe('app');

      // Outer context unchanged
      expect(getContext().area).toBeNull();
      expect(getContext().operationId).toBeNull();
    });

    it('merges fields', () => {
      setDefaultContext({ application: 'app', component: 'svc' });
      setFields({ base: true });

      let innerFields: Record<string, unknown> = {};
      withContext({ fields: { extra: 1 } }, () => {
        innerFields = getContext().fields;
      });

      expect(innerFields).toEqual({ base: true, extra: 1 });
    });
  });
});
