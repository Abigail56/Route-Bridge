/**
 * Loud alert sounds for the Admin (a new order, someone asking to join, any new notification), made by the browser itself
 * (Web Audio), so there is no sound file to download.
 *
 * Browsers only allow sound after the person has clicked or typed on the page once, so `unlockOrderChime` gets the sound
 * ready on the first touch. Until then the chime stays silent (the "New order" pop-up still shows). Any failure is
 * swallowed: no sound is better than a broken console.
 */
type AudioContextClass = typeof AudioContext;
let context: AudioContext | null = null;
let lastPlayed = 0; // when any chime last played, so one event never sounds twice
let announcePending = false; // an alert came while the browser still blocked sound: play it the moment sound is allowed
// high-low four times over (about two seconds): impossible to miss
const ALERT: ReadonlyArray<readonly [number, number]> = [[988, 0], [740, 0.25], [988, 0.5], [740, 0.75], [988, 1.1], [740, 1.35], [988, 1.6], [740, 1.85]];

/** True once the browser lets this page play sound (after the first click or key press, or the sound button). */
export function soundOn(): boolean { return context?.state === 'running'; }

function audio(): AudioContext | null {
  if (context) return context;
  if (typeof window === 'undefined') return null;
  const Ctx: AudioContextClass | undefined = window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioContextClass }).webkitAudioContext;
  context = Ctx ? new Ctx() : null;
  return context;
}

// Loud and clear, so it is heard across a room or a noisy shop: every note is a bright square wave doubled an octave up,
// held at near full volume, and all of it goes through a compressor that keeps the level high without crackling.
const PEAK = 0.9;
const NOTE_SECONDS = 0.42;
let output: AudioNode | null = null;

function loudOutput(ctx: AudioContext): AudioNode {
  if (output) return output;
  const squeeze = ctx.createDynamicsCompressor();
  squeeze.threshold.value = -18;
  squeeze.knee.value = 6;
  squeeze.ratio.value = 8;
  squeeze.attack.value = 0.002;
  squeeze.release.value = 0.12;
  const master = ctx.createGain();
  master.gain.value = 1;
  squeeze.connect(master).connect(ctx.destination);
  output = squeeze;
  return output;
}

function play(notes: ReadonlyArray<readonly [number, number]>): void {
  lastPlayed = Date.now();
  try {
    const ctx = audio();
    if (!ctx) return;
    if (ctx.state === 'suspended') void ctx.resume().catch(() => undefined);
    const out = loudOutput(ctx);
    const start = ctx.currentTime + 0.02;
    for (const [frequency, offset] of notes) {
      const at = start + offset;
      const volume = ctx.createGain();
      volume.gain.setValueAtTime(0.0001, at);
      volume.gain.exponentialRampToValueAtTime(PEAK, at + 0.01);
      volume.gain.setValueAtTime(PEAK, at + NOTE_SECONDS * 0.6);
      volume.gain.exponentialRampToValueAtTime(0.0001, at + NOTE_SECONDS);
      volume.connect(out);
      for (const [type, pitch, level] of [['square', frequency, 0.55], ['triangle', frequency * 2, 0.45]] as const) {
        const tone = ctx.createOscillator();
        const mix = ctx.createGain();
        tone.type = type;
        tone.frequency.value = pitch;
        mix.gain.value = level;
        tone.connect(mix).connect(volume);
        tone.start(at);
        tone.stop(at + NOTE_SECONDS + 0.05);
      }
    }
  } catch {
    // ignore
  }
}

/** A new order: two rising notes, played twice (about a second and a half). */
export function playOrderChime(): void { play([[880, 0], [1320, 0.25], [880, 0.6], [1320, 0.85]]); }

/** A new shop or rider asking to be added: four rising notes, so it sounds different from an order. */
export function playJoinChime(): void { play([[660, 0], [880, 0.22], [1100, 0.44], [1320, 0.66]]); }

/** A new notification in the bell (a rider waiting for a code, a failed delivery, a shop's problem…): a high-low-high alert.
 *  Skipped when another chime played in the last 3 seconds, because that one already announced the same event. */
export function playAlertChime(): void {
  if (!soundOn()) { announcePending = true; return; }
  if (Date.now() - lastPlayed < 3000) return;
  play(ALERT);
}

/** Notifications were already waiting when the console opened: play the alert now, or as soon as the browser allows sound. */
export function announceWhenSoundOn(): void { if (soundOn()) play(ALERT); else announcePending = true; }

/** The sound button (a click, so the browser allows it): switch sound on and play the alert so the person hears it works. */
export async function enableSound(): Promise<boolean> {
  try {
    const ctx = audio();
    if (!ctx) return false;
    await ctx.resume();
    announcePending = false;
    play(ALERT);
    return ctx.state === 'running';
  } catch { return false; }
}

/** Call once when the console opens: the first click or key press anywhere makes later chimes audible. Returns a cleanup. */
export function unlockOrderChime(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const unlock = () => {
    try {
      const ctx = audio();
      const ready = ctx && ctx.state === 'suspended' ? ctx.resume() : Promise.resolve();
      void ready.then(() => { if (announcePending && soundOn()) { announcePending = false; play(ALERT); } }).catch(() => undefined);
    } catch { /* ignore */ }
    stop();
  };
  const stop = () => { window.removeEventListener('pointerdown', unlock); window.removeEventListener('keydown', unlock); };
  window.addEventListener('pointerdown', unlock);
  window.addEventListener('keydown', unlock);
  return stop;
}
