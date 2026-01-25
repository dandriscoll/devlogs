import { describe, it, expect } from 'vitest';
import {
  resolveBuildInfo,
  resolveBuildId,
  createBuildInfoData,
  formatTimestamp,
  type BuildInfoFile,
} from './build-info';

// Fixed date for deterministic tests
const FIXED_DATE = new Date('2026-01-24T15:30:45.000Z');
const FIXED_TIMESTAMP = '20260124T153045Z';
const fixedNow = () => FIXED_DATE;

describe('formatTimestamp', () => {
  it('formats UTC date correctly', () => {
    const date = new Date('2026-03-15T10:20:30.000Z');
    expect(formatTimestamp(date)).toBe('20260315T102030Z');
  });

  it('ignores milliseconds', () => {
    const date = new Date('2026-03-15T10:20:30.123Z');
    expect(formatTimestamp(date)).toBe('20260315T102030Z');
  });

  it('pads single digit values', () => {
    const date = new Date('2026-01-05T09:08:07.000Z');
    expect(formatTimestamp(date)).toBe('20260105T090807Z');
  });
});

describe('resolveBuildInfo', () => {
  describe('env BUILD_ID precedence', () => {
    it('env BUILD_ID overrides everything', () => {
      const data: BuildInfoFile = {
        build_id: 'file-build-id',
        branch: 'file-branch',
        timestamp_utc: '20260101T000000Z',
      };

      const result = resolveBuildInfo({
        data,
        env: {
          DEVLOGS_BUILD_ID: 'env-build-id-override',
          DEVLOGS_BRANCH: 'env-branch',
        },
        nowFn: fixedNow,
      });

      expect(result.buildId).toBe('env-build-id-override');
      expect(result.branch).toBe('env-branch');
      expect(result.source).toBe('env');
      expect(result.path).toBeNull();
    });

    it('env BUILD_ID works without other env vars', () => {
      const result = resolveBuildInfo({
        env: { DEVLOGS_BUILD_ID: 'direct-build-id' },
        nowFn: fixedNow,
      });

      expect(result.buildId).toBe('direct-build-id');
      expect(result.branch).toBeNull();
      expect(result.timestampUtc).toBe(FIXED_TIMESTAMP);
      expect(result.source).toBe('env');
    });
  });

  describe('env branch and timestamp', () => {
    it('env branch generates build_id', () => {
      const result = resolveBuildInfo({
        env: { DEVLOGS_BRANCH: 'feature/my-feature' },
        nowFn: fixedNow,
      });

      expect(result.buildId).toBe(`feature/my-feature-${FIXED_TIMESTAMP}`);
      expect(result.branch).toBe('feature/my-feature');
      expect(result.timestampUtc).toBe(FIXED_TIMESTAMP);
      expect(result.source).toBe('env');
    });

    it('env timestamp is used', () => {
      const result = resolveBuildInfo({
        env: {
          DEVLOGS_BRANCH: 'main',
          DEVLOGS_BUILD_TIMESTAMP_UTC: '20250101T120000Z',
        },
        nowFn: fixedNow,
      });

      expect(result.buildId).toBe('main-20250101T120000Z');
      expect(result.timestampUtc).toBe('20250101T120000Z');
      expect(result.source).toBe('env');
    });

    it('custom env prefix works', () => {
      const result = resolveBuildInfo({
        envPrefix: 'MYAPP_',
        env: { MYAPP_BUILD_ID: 'custom-prefix-id' },
        nowFn: fixedNow,
      });

      expect(result.buildId).toBe('custom-prefix-id');
      expect(result.source).toBe('env');
    });
  });

  describe('data provides build info', () => {
    it('data provides all fields', () => {
      const data: BuildInfoFile = {
        build_id: 'file-build-123',
        branch: 'develop',
        timestamp_utc: '20260115T093000Z',
      };

      const result = resolveBuildInfo({ data, nowFn: fixedNow });

      expect(result.buildId).toBe('file-build-123');
      expect(result.branch).toBe('develop');
      expect(result.timestampUtc).toBe('20260115T093000Z');
      expect(result.source).toBe('file');
    });

    it('data with extra keys works', () => {
      const data: BuildInfoFile = {
        build_id: 'build-with-extras',
        branch: 'main',
        timestamp_utc: '20260115T093000Z',
        commit: 'abc123',
        pipeline_id: 12345,
      };

      const result = resolveBuildInfo({ data, nowFn: fixedNow });

      expect(result.buildId).toBe('build-with-extras');
      expect(result.source).toBe('file');
    });
  });

  describe('env overrides data', () => {
    it('env branch overrides data branch', () => {
      const data: BuildInfoFile = {
        build_id: 'file-build-id',
        branch: 'file-branch',
        timestamp_utc: '20260115T093000Z',
      };

      const result = resolveBuildInfo({
        data,
        env: { DEVLOGS_BRANCH: 'env-branch-override' },
        nowFn: fixedNow,
      });

      expect(result.buildId).toBe('file-build-id');
      expect(result.branch).toBe('env-branch-override');
      expect(result.source).toBe('file');
    });

    it('env timestamp overrides data timestamp', () => {
      const data: BuildInfoFile = {
        build_id: 'file-build-id',
        branch: 'main',
        timestamp_utc: '20260115T093000Z',
      };

      const result = resolveBuildInfo({
        data,
        env: { DEVLOGS_BUILD_TIMESTAMP_UTC: '20250505T555555Z' },
        nowFn: fixedNow,
      });

      expect(result.buildId).toBe('file-build-id');
      expect(result.timestampUtc).toBe('20250505T555555Z');
      expect(result.source).toBe('file');
    });
  });

  describe('invalid data handling', () => {
    it('empty data falls back to generated', () => {
      const result = resolveBuildInfo({ data: {}, nowFn: fixedNow });

      expect(result.buildId).toBe(`unknown-${FIXED_TIMESTAMP}`);
      expect(result.source).toBe('generated');
    });

    it('data without build_id falls back to generated', () => {
      const data: BuildInfoFile = {
        branch: 'main',
        timestamp_utc: '20260115T093000Z',
      };

      const result = resolveBuildInfo({ data, nowFn: fixedNow });

      expect(result.buildId).toBe(`unknown-${FIXED_TIMESTAMP}`);
      expect(result.source).toBe('generated');
    });

    it('no options generates default', () => {
      const result = resolveBuildInfo({ nowFn: fixedNow });

      expect(result.buildId).toBe(`unknown-${FIXED_TIMESTAMP}`);
      expect(result.branch).toBeNull();
      expect(result.source).toBe('generated');
    });
  });

  describe('deterministic build_id', () => {
    it('same nowFn gives same result', () => {
      const result1 = resolveBuildInfo({ nowFn: fixedNow });
      const result2 = resolveBuildInfo({ nowFn: fixedNow });

      expect(result1.buildId).toBe(result2.buildId);
      expect(result1.timestampUtc).toBe(result2.timestampUtc);
    });

    it('different nowFn gives different result', () => {
      const otherDate = new Date('2025-06-15T12:00:00.000Z');
      const otherNow = () => otherDate;

      const result1 = resolveBuildInfo({ nowFn: fixedNow });
      const result2 = resolveBuildInfo({ nowFn: otherNow });

      expect(result1.buildId).not.toBe(result2.buildId);
      expect(result1.timestampUtc).toBe(FIXED_TIMESTAMP);
      expect(result2.timestampUtc).toBe('20250615T120000Z');
    });
  });
});

describe('resolveBuildId', () => {
  it('returns string only', () => {
    const result = resolveBuildId({ nowFn: fixedNow });

    expect(typeof result).toBe('string');
    expect(result).toBe(`unknown-${FIXED_TIMESTAMP}`);
  });

  it('passes all options', () => {
    const result = resolveBuildId({
      envPrefix: 'MYAPP_',
      env: { MYAPP_BUILD_ID: 'custom-id' },
      nowFn: fixedNow,
    });

    expect(result).toBe('custom-id');
  });
});

describe('createBuildInfoData', () => {
  it('creates data with unknown branch by default', () => {
    const data = createBuildInfoData({ nowFn: fixedNow });

    expect(data.build_id).toBe(`unknown-${FIXED_TIMESTAMP}`);
    expect(data.branch).toBeUndefined();
    expect(data.timestamp_utc).toBe(FIXED_TIMESTAMP);
  });

  it('creates data with explicit branch', () => {
    const data = createBuildInfoData({
      branch: 'release/v1.0',
      nowFn: fixedNow,
    });

    expect(data.build_id).toBe(`release/v1.0-${FIXED_TIMESTAMP}`);
    expect(data.branch).toBe('release/v1.0');
    expect(data.timestamp_utc).toBe(FIXED_TIMESTAMP);
  });
});
