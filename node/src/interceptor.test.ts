import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { interceptConsole, restoreConsole, originalConsole } from './interceptor';
import { setDefaultContext, resetContext, withOperation, getContext } from './context';
import type { DevlogsClient } from './client';
import type { LogDocument } from './types';

describe('interceptConsole', () => {
  let sentDocs: LogDocument[];
  let mockClient: DevlogsClient;

  beforeEach(() => {
    sentDocs = [];
    mockClient = {
      send: (doc: LogDocument) => sentDocs.push(doc),
    } as unknown as DevlogsClient;

    resetContext();
    setDefaultContext({
      application: 'test',
      component: 'test-svc',
    });
    interceptConsole(mockClient);
  });

  afterEach(() => {
    restoreConsole();
    resetContext();
  });

  it('intercepts console.log and sends document', () => {
    console.log('test message');
    expect(sentDocs.length).toBe(1);
    expect(sentDocs[0].message).toBe('test message');
    expect(sentDocs[0].level).toBe('info');
    expect(sentDocs[0].application).toBe('test');
  });

  it('intercepts all console methods', () => {
    console.log('a');
    console.warn('b');
    console.error('c');
    console.debug('d');
    console.info('e');
    expect(sentDocs.length).toBe(5);
    expect(sentDocs.map((d) => d.level)).toEqual([
      'info',
      'warning',
      'error',
      'debug',
      'info',
    ]);
  });

  it('still calls original console', () => {
    const spy = vi.spyOn(originalConsole, 'log');
    console.log('hello');
    expect(spy).toHaveBeenCalledWith('hello');
    spy.mockRestore();
  });

  it('reads context from AsyncLocalStorage', async () => {
    await withOperation('req-42', async () => {
      console.log('inside operation');
    });

    expect(sentDocs.length).toBe(1);
    expect(sentDocs[0].operation_id).toBe('req-42');
  });

  it('restoreConsole undoes interception', () => {
    restoreConsole();
    console.log('after restore');
    expect(sentDocs.length).toBe(0);
  });
});
