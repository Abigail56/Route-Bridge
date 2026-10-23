import { describe, expect, it } from 'vitest';
import { newJobs, seenJobs } from './new-jobs';

const job = (job_id: string, status = 'assigned') => ({ job_id, status });

describe('new delivery alarm for riders', () => {
  it('stays quiet when the app first opens', () => {
    expect(newJobs(null, [job('a')])).toEqual([]);
  });

  it('rings for each job given since the last look', () => {
    const seen = seenJobs([job('a')]);
    expect(newJobs(seen, [job('a'), job('b'), job('c', 'en_route')]).map((j) => j.job_id)).toEqual(['b', 'c']);
  });

  it('ignores jobs that are already finished', () => {
    expect(newJobs(seenJobs([]), [job('d', 'delivered'), job('e', 'cancelled')])).toEqual([]);
  });
});
