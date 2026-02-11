import { describe, it, expect } from 'vitest';
import { parseDevlogsUrl } from './url-parser';

describe('parseDevlogsUrl', () => {
  describe('OpenSearch mode', () => {
    it('detects user:pass as OpenSearch', () => {
      const config = parseDevlogsUrl('http://admin:secret@localhost:9200');
      expect(config.mode).toBe('opensearch');
      if (config.mode === 'opensearch') {
        expect(config.scheme).toBe('http');
        expect(config.host).toBe('localhost');
        expect(config.port).toBe(9200);
        expect(config.user).toBe('admin');
        expect(config.password).toBe('secret');
        expect(config.index).toBe('devlogs-0001');
      }
    });

    it('parses opensearchs:// as HTTPS OpenSearch', () => {
      const config = parseDevlogsUrl('opensearchs://admin:pass@os.example.com');
      expect(config.mode).toBe('opensearch');
      if (config.mode === 'opensearch') {
        expect(config.scheme).toBe('https');
        expect(config.host).toBe('os.example.com');
        expect(config.port).toBe(443);
        expect(config.user).toBe('admin');
        expect(config.password).toBe('pass');
      }
    });

    it('parses opensearch:// as HTTP OpenSearch', () => {
      const config = parseDevlogsUrl('opensearch://admin:pass@localhost');
      expect(config.mode).toBe('opensearch');
      if (config.mode === 'opensearch') {
        expect(config.scheme).toBe('http');
        expect(config.port).toBe(9200);
      }
    });

    it('extracts index from path', () => {
      const config = parseDevlogsUrl(
        'opensearchs://admin:pass@host:9200/my-index'
      );
      expect(config.mode).toBe('opensearch');
      if (config.mode === 'opensearch') {
        expect(config.index).toBe('my-index');
      }
    });

    it('uses explicit index over path', () => {
      const config = parseDevlogsUrl(
        'http://admin:pass@host:9200/path-index',
        'explicit-index'
      );
      if (config.mode === 'opensearch') {
        expect(config.index).toBe('explicit-index');
      }
    });

    it('decodes URL-encoded credentials', () => {
      const config = parseDevlogsUrl(
        'http://my%40user:p%40ss@host:9200'
      );
      if (config.mode === 'opensearch') {
        expect(config.user).toBe('my@user');
        expect(config.password).toBe('p@ss');
      }
    });
  });

  describe('Collector mode', () => {
    it('detects token-only URL as collector', () => {
      const config = parseDevlogsUrl('https://mytoken@collector.example.com:8080');
      expect(config.mode).toBe('collector');
      if (config.mode === 'collector') {
        expect(config.scheme).toBe('https');
        expect(config.host).toBe('collector.example.com');
        expect(config.port).toBe(8080);
        expect(config.token).toBe('mytoken');
      }
    });

    it('detects no-credentials URL as collector', () => {
      const config = parseDevlogsUrl('http://collector.local:8080');
      expect(config.mode).toBe('collector');
      if (config.mode === 'collector') {
        expect(config.token).toBeNull();
        expect(config.port).toBe(8080);
      }
    });

    it('defaults HTTPS port to 443', () => {
      const config = parseDevlogsUrl('https://collector.example.com');
      expect(config.mode).toBe('collector');
      if (config.mode === 'collector') {
        expect(config.port).toBe(443);
      }
    });

    it('defaults HTTP port to 9200', () => {
      const config = parseDevlogsUrl('http://localhost');
      if (config.mode === 'collector') {
        expect(config.port).toBe(9200);
      }
    });
  });
});
