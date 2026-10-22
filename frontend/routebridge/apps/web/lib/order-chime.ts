/**
 * A short two-note chime for a new order, made by the browser itself (Web Audio), so there is no sound file to download.
 *
 * Browsers only allow sound after the person has clicked or typed on the page once, so `unlockOrderChime` gets the sound
 * ready on the first touch. Until then the chime stays silent (the "New order" pop-up still shows). Any failure is
 * swallowed: no sound is better than a broken console.
 */
type AudioContextClass = typeof AudioContext;
let context: AudioContext | null = null;

function audio(): AudioContext | null {
  if (context) return context;
  if (typeof window === 'undefined') return null;
  const Ctx: AudioContextClass | undefined = window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioContextClass }).webkitAudioContext;
  context = Ctx ? new Ctx() : null;
  return context;
}

function play(notes: ReadonlyArray<readonly [number, number]>): void {
  try {
    const ctx = audio();
    if (!ctx) return;
    if (ctx.state === 'suspended') void ctx.resume().catch(() => undefined);
    const start = ctx.currentTime + 0.02;
    for (const [frequency, offset] of notes) {
      const tone = ctx.createOscillator();
      const volume = ctx.createGain();
      tone.type = 'sine';
      tone.frequency.value = frequency;
      volume.gain.setValueAtTime(0.0001, start + offset);
      volume.gain.exponentialRampToValueAtTime(0.25, start + offset + 0.02);
      volume.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.35);
      tone.connect(volume).connect(ctx.destination);
      tone.start(start + offset);
      tone.stop(start + offset + 0.4);
    }
  } catch {
    // ignore
  }
}

/** A new order: two rising notes, about half a second in all. */
export function playOrderChime(): void { play([[880, 0], [1320, 0.18]]); }

/** A new shop or rider asking to be added: three notes, so it sounds different from an order. */
export function playJoinChime(): void { play([[660, 0], [880, 0.16], [1100, 0.32]]); }

/** Call once when the console opens: the first click or key press anywhere makes later chimes audible. Returns a cleanup. */
export function unlockOrderChime(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const unlock = () => {
    try { const ctx = audio(); if (ctx && ctx.state === 'suspended') void ctx.resume().catch(() => undefined); } catch { /* ignore */ }
    stop();
  };
  const stop = () => { window.removeEventListener('pointerdown', unlock); window.removeEventListener('keydown', unlock); };
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);
  return stop;
}
