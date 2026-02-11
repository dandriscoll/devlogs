import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { loadEnvConfig, resetDotenvLoaded } from './config';

describe('loadEnvConfig', () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    resetDotenvLoaded();
    // Clear all DEVLOGS_ vars
    for (const key of Object.keys(process.env)) {
      if (key.startsWith('DEVLOGS_')) {
        delete process.env[key];
      }
    }
  });

  afterEach(() => {
    // Restore original env
    for (const key of Object.keys(process.env)) {
      if (key.startsWith('DEVLOGS_') || key === 'DOTENV_PATH') {
        delete process.env[key];
      }
    }
    Object.assign(process.env, originalEnv);
    resetDotenvLoaded();
  });

  it('returns undefined fields when no env vars set', () => {
    const config = loadEnvConfig();
    expect(config.url).toBeUndefined();
    expect(config.application).toBeUndefined();
    expect(config.component).toBeUndefined();
  });

  it('reads DEVLOGS_* env vars', () => {
    process.env.DEVLOGS_URL = 'http://admin:admin@localhost:9200';
    process.env.DEVLOGS_APPLICATION = 'my-app';
    process.env.DEVLOGS_COMPONENT = 'api';
    process.env.DEVLOGS_INDEX = 'my-index';
    process.env.DEVLOGS_AREA = 'auth';
    process.env.DEVLOGS_ENVIRONMENT = 'production';
    process.env.DEVLOGS_VERSION = '1.0.0';

    const config = loadEnvConfig();
    expect(config.url).toBe('http://admin:admin@localhost:9200');
    expect(config.application).toBe('my-app');
    expect(config.component).toBe('api');
    expect(config.index).toBe('my-index');
    expect(config.area).toBe('auth');
    expect(config.environment).toBe('production');
    expect(config.version).toBe('1.0.0');
  });
});
