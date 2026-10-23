import type { DriverJob } from './api';

/** Jobs the rider still has to do (a new assignment arrives in one of these states). */
const OPEN = new Set(['assigned', 'rescheduled', 'accepted', 'en_route', 'arrived']);

export const seenJobs = (jobs: Pick<DriverJob, 'job_id'>[]): Set<string> => new Set(jobs.map((job) => job.job_id));

/** Jobs dispatch gave the rider since the last look. The first look (seen = null) says nothing, so opening the app stays quiet. */
export function newJobs<T extends Pick<DriverJob, 'job_id' | 'status'>>(seen: Set<string> | null, jobs: T[]): T[] {
  if (seen === null) return [];
  return jobs.filter((job) => !seen.has(job.job_id) && OPEN.has(job.status));
}
