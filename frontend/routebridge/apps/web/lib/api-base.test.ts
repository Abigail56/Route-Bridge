import { describe, expect, it } from 'vitest';
import { apiBaseUrl } from './api';

describe('apiBaseUrl', () => {
  it('uses the configured address, or localhost when nothing is set', () => {
    expect(apiBaseUrl('https://api.example.test')).toBe('https://api.example.test');
    expect(apiBaseUrl(undefined)).toBe('http://localhost:8000');
    expect(apiBaseUrl('')).toBe('http://localhost:8000');
  });

  it('same-origin means the page calls its own address', () => {
    expect(apiBaseUrl('same-origin')).toBe('');
    expect(`${apiBaseUrl('same-origin')}/api/v1/auth/me`).toBe('/api/v1/auth/me');
  });
});
