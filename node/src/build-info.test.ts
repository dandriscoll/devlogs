import { describe, it, expect } from 'vitest';
import {
  formatTimestamp,
  resolveBuildInfo,
  resolveBuildId,
  createBuildInfoData,
} from './build-info';

const fixedDate = new Date('2026-01-24T15:30:45.000Z');
const fixedNow = () => fixedDate;

describe('formatTimestamp', () => {
  it('formats a date as YYYYMMDDTHHMMSSZ', () => {
    expect(formatTimestamp(fixedDate)).toBe('20260124T153045Z');
  });

  it('pads single-digit months and days', () => {
    const d = new Date('2026-03-05T08:01:02.000Z');
    expect(formatTimestamp(d)).toBe('20260305T080102Z');
  });
});

describe('resolveBuildInfo', () => {
  it('generates build info when no env vars set', () => {
    const bi = resolveBuildInfo({ nowFn: fixedNow, env: {} });
    expect(bi.source).toBe('generated');
    expect(bi.buildId).toBe('unknown-20260124T153045Z');
    expect(bi.branch).toBeNull();
    expect(bi.timestampUtc).toBe('20260124T153045Z');
  });

  it('uses BUILD_ID env var (highest precedence)', () => {
    const bi = resolveBuildInfo({
      nowFn: fixedNow,
      env: { DEVLOGS_BUILD_ID: 'ci-123' },
    });
    expect(bi.source).toBe('env');
    expect(bi.buildId).toBe('ci-123');
  });

  it('uses data from file', () => {
    const bi = resolveBuildInfo({
      nowFn: fixedNow,
      env: {},
      data: { build_id: 'file-build', branch: 'main' },
    });
    expect(bi.source).toBe('file');
    expect(bi.buildId).toBe('file-build');
    expect(bi.branch).toBe('main');
  });

  it('uses branch from env', () => {
    const bi = resolveBuildInfo({
      nowFn: fixedNow,
      env: { DEVLOGS_BRANCH: 'feature-x' },
    });
    expect(bi.source).toBe('env');
    expect(bi.branch).toBe('feature-x');
    expect(bi.buildId).toBe('feature-x-20260124T153045Z');
  });
});

describe('resolveBuildId', () => {
  it('returns a string', () => {
    const id = resolveBuildId({ nowFn: fixedNow, env: {} });
    expect(typeof id).toBe('string');
    expect(id.length).toBeGreaterThan(0);
  });
});

describe('createBuildInfoData', () => {
  it('creates build info data object', () => {
    const data = createBuildInfoData({ nowFn: fixedNow });
    expect(data.build_id).toBe('unknown-20260124T153045Z');
    expect(data.timestamp_utc).toBe('20260124T153045Z');
  });

  it('includes branch when provided', () => {
    const data = createBuildInfoData({ branch: 'main', nowFn: fixedNow });
    expect(data.build_id).toBe('main-20260124T153045Z');
    expect(data.branch).toBe('main');
  });
});
