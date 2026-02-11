import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { init, destroy, isInitialized, setArea, setOperationId } from './index';

describe('init / destroy', () => {
  afterEach(() => {
    destroy();
    // Clean env
    delete process.env.DEVLOGS_URL;
    delete process.env.DEVLOGS_APPLICATION;
    delete process.env.DEVLOGS_COMPONENT;
  });

  it('starts uninitialized', () => {
    expect(isInitialized()).toBe(false);
  });

  it('initializes with explicit options', () => {
    init({
      url: 'http://admin:admin@localhost:9200',
      application: 'test-app',
      component: 'test',
    });
    expect(isInitialized()).toBe(true);
  });

  it('destroy resets state', () => {
    init({
      url: 'http://admin:admin@localhost:9200',
      application: 'test-app',
      component: 'test',
    });
    destroy();
    expect(isInitialized()).toBe(false);
  });

  it('does not initialize without url', () => {
    init({ application: 'app', component: 'svc' });
    expect(isInitialized()).toBe(false);
  });

  it('does not initialize without application', () => {
    init({ url: 'http://admin:admin@localhost:9200', component: 'svc' });
    expect(isInitialized()).toBe(false);
  });

  it('does not initialize without component', () => {
    init({ url: 'http://admin:admin@localhost:9200', application: 'app' });
    expect(isInitialized()).toBe(false);
  });
});
