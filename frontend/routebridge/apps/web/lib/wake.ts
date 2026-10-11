/**
 * Free hosting puts the backend to sleep after about 15 quiet minutes, and the first request then takes up to a minute while it wakes.
 * The website gives up on a slow backend after about 30 seconds and shows a 502 ("bad gateway"), so the first person to sign in saw an error.
 * These helpers let the page notice that, say so, and try again by itself.
 */
const GATEWAY_ERRORS = new Set([502, 503, 504]);

/** 502, 503 and 504 mean "the server behind this one did not answer in time": the backend is waking up or restarting. */
export const isGatewayError = (status: number): boolean => GATEWAY_ERRORS.has(status);

type WakeOptions = { onWaiting?: () => void; sleep?: (ms: number) => Promise<void>; tries?: number; gapMs?: number };

/**
 * Ask the backend something harmless until it answers. Returns true as soon as it gives ANY answer other than a gateway error
 * (a 401 "sign in first" is a perfectly good answer: it means the backend is awake). `onWaiting` is called once, the first time it is asleep.
 * Returns false if it still has not woken after all the tries; the caller then carries on and shows the normal error.
 */
export async function wakeServer(probe: () => Promise<number>, options: WakeOptions = {}): Promise<boolean> {
  const { onWaiting, sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)), tries = 10, gapMs = 6000 } = options;
  for (let attempt = 0; attempt < tries; attempt++) {
    let status = 0;
    try { status = await probe(); } catch { status = 0; } // no answer at all: treat like asleep
    if (status !== 0 && !isGatewayError(status)) return true;
    if (attempt === 0) onWaiting?.();
    if (attempt < tries - 1) await sleep(gapMs);
  }
  return false;
}
