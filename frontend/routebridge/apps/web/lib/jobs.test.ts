import { describe, expect, it } from 'vitest';
import { filterJobs, toStatus, worksIn, type Job, type Status } from './jobs';

describe('worksIn (a rider matches an order zone)', () => {
  it('matches when the rider covers the zone', () => {
    expect(worksIn({ zone_ids: ['lagos', 'abuja'] }, 'lagos')).toBe(true);
    expect(worksIn({ zone_ids: ['abuja'] }, 'lagos')).toBe(false);
  });
  it('a rider with no zones set covers every zone', () => {
    expect(worksIn({ zone_ids: [] }, 'lagos')).toBe(true);
    expect(worksIn({}, 'lagos')).toBe(true);
  });
  it('an order with no zone can go to anyone', () => {
    expect(worksIn({ zone_ids: ['abuja'] }, null)).toBe(true);
  });
});

describe('the order list filter', () => {
  const job = (status: Status, extra: Partial<Job> = {}) => ({ status, order: 'RB-1', customer: 'Ada', merchant: 'Shop', area: 'Yaba', landmark: '', driver: undefined, ...extra }) as Job;
  const jobs = [job('pending'), job('assigned'), job('accepted'), job('en_route'), job('arrived'), job('delivered'), job('exception', { customer: 'Bola' })];

  it('keeps accepted apart from assigned', () => {
    expect(toStatus('accepted')).toBe('accepted');
    expect(toStatus('assigned')).toBe('assigned');
  });
  it('"active" covers every stage between assigned and the door', () => {
    expect(filterJobs(jobs, 'active', '').map((j) => j.status)).toEqual(['assigned', 'accepted', 'en_route', 'arrived']);
  });
  it('a single status and the search box combine', () => {
    expect(filterJobs(jobs, 'delivered', '')).toHaveLength(1);
    expect(filterJobs(jobs, 'all', 'bola').map((j) => j.status)).toEqual(['exception']);
    expect(filterJobs(jobs, 'pending', 'bola')).toHaveLength(0);
  });
});
