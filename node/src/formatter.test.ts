import { describe, it, expect } from 'vitest';
import { formatLogDocument, extractSourceLocation } from './formatter';
import type { LogContext } from './types';

describe('formatLogDocument', () => {
  const baseContext: LogContext = {
    application: 'test-app',
    component: 'api',
    area: null,
    operationId: null,
    environment: null,
    version: null,
    fields: {},
  };

  it('formats a basic log entry', () => {
    const doc = formatLogDocument('log', ['Hello world'], baseContext);

    expect(doc.doc_type).toBe('log_entry');
    expect(doc.application).toBe('test-app');
    expect(doc.component).toBe('api');
    expect(doc.message).toBe('Hello world');
    expect(doc.level).toBe('info');
    expect(doc.area).toBeNull();
    expect(doc.operation_id).toBeNull();
    expect(doc.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(doc.source.logger).toBe('node');
    expect(doc.process.id).toBe(process.pid);
  });

  it('normalizes log levels', () => {
    expect(formatLogDocument('warn', ['x'], baseContext).level).toBe('warning');
    expect(formatLogDocument('log', ['x'], baseContext).level).toBe('info');
    expect(formatLogDocument('error', ['x'], baseContext).level).toBe('error');
    expect(formatLogDocument('debug', ['x'], baseContext).level).toBe('debug');
    expect(formatLogDocument('info', ['x'], baseContext).level).toBe('info');
  });

  it('joins multiple args into message', () => {
    const doc = formatLogDocument('log', ['Hello', 'world', 42], baseContext);
    expect(doc.message).toBe('Hello world 42');
  });

  it('formats Error args', () => {
    const doc = formatLogDocument('error', [new Error('boom')], baseContext);
    expect(doc.message).toBe('Error: boom');
  });

  it('stringifies object args', () => {
    const doc = formatLogDocument('log', [{ key: 'val' }], baseContext);
    expect(doc.message).toBe('{"key":"val"}');
  });

  it('includes context fields', () => {
    const ctx: LogContext = {
      ...baseContext,
      fields: { requestId: 'abc' },
    };
    const doc = formatLogDocument('log', ['msg'], ctx);
    expect(doc.fields).toEqual({ requestId: 'abc' });
  });

  it('merges last-arg object into fields', () => {
    const doc = formatLogDocument(
      'log',
      ['msg', { userId: 42 }],
      baseContext
    );
    expect(doc.fields).toEqual({ userId: 42 });
  });

  it('includes optional metadata when set', () => {
    const ctx: LogContext = {
      ...baseContext,
      area: 'auth',
      operationId: 'op-1',
      environment: 'prod',
      version: '2.0.0',
    };
    const doc = formatLogDocument('log', ['msg'], ctx);
    expect(doc.area).toBe('auth');
    expect(doc.operation_id).toBe('op-1');
    expect(doc.environment).toBe('prod');
    expect(doc.version).toBe('2.0.0');
  });

  it('omits environment/version when null', () => {
    const doc = formatLogDocument('log', ['msg'], baseContext);
    expect(doc).not.toHaveProperty('environment');
    expect(doc).not.toHaveProperty('version');
  });
});

describe('extractSourceLocation', () => {
  it('returns a source object', () => {
    const source = extractSourceLocation();
    expect(source.logger).toBe('node');
    // When called from a test file, should have a pathname
    expect(source.pathname).toBeTruthy();
    expect(source.lineno).toBeGreaterThan(0);
  });
});
