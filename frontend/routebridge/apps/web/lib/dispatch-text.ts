import type { AutoAssignResult } from './api';

/** Plain-language outcome of an automatic assignment, so nobody has to guess why a job did or did not get a rider. */
export function describeAutoAssign(result: AutoAssignResult): string {
  if (result.assigned) {
    if (result.method === 'nearest' && result.distance_m !== null) return `Assigned to ${result.driver_name}, about ${(result.distance_m / 1000).toFixed(1)} km away.`;
    return `Assigned to ${result.driver_name}, the rider who has been free the longest (this address has no map position yet).`;
  }
  if (result.reason === 'no_available_driver') return 'No rider is free right now. Try again when one finishes a delivery.';
  if (result.reason === 'no_driver_nearby') return 'No free rider is close enough to this address. Pick one by hand, or wait for a rider to get closer.';
  if (result.reason === 'not_waiting') return 'This job already has a rider.';
  return 'Could not assign a rider.';
}
