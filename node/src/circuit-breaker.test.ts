import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CircuitBreaker } from './circuit-breaker';

describe('CircuitBreaker', () => {
  let messages: string[];
  let cb: CircuitBreaker;

  beforeEach(() => {
    messages = [];
    cb = new CircuitBreaker(100, 50, (msg) => messages.push(msg));
  });

  it('starts closed', () => {
    expect(cb.shouldSkip()).toBe(false);
  });

  it('opens on failure', () => {
    cb.recordFailure(new Error('connection refused'));
    expect(cb.shouldSkip()).toBe(true);
  });

  it('closes on success', () => {
    cb.recordFailure(new Error('fail'));
    expect(cb.shouldSkip()).toBe(true);

    cb.recordSuccess();
    expect(cb.shouldSkip()).toBe(false);
  });

  it('auto-resets after duration', async () => {
    cb = new CircuitBreaker(50, 10, (msg) => messages.push(msg));
    cb.recordFailure(new Error('fail'));
    expect(cb.shouldSkip()).toBe(true);

    await new Promise((r) => setTimeout(r, 60));
    expect(cb.shouldSkip()).toBe(false);
  });

  it('throttles error output', () => {
    cb.recordFailure(new Error('err1'));
    cb.recordFailure(new Error('err2'));
    cb.recordFailure(new Error('err3'));

    // Only one error message within the interval
    expect(messages.length).toBe(1);
    expect(messages[0]).toContain('Failed to index log');
  });

  it('prints recovery message', () => {
    cb.recordFailure(new Error('fail'));
    messages.length = 0; // clear failure message

    cb.recordSuccess();
    expect(messages.length).toBe(1);
    expect(messages[0]).toContain('Connection restored');
  });

  it('does not print recovery if already closed', () => {
    cb.recordSuccess(); // was never open
    expect(messages.length).toBe(0);
  });
});
