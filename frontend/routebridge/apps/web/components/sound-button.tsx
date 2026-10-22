'use client';

import { useEffect, useState } from 'react';
import { enableSound, soundOn } from '../lib/order-chime';

/**
 * Browsers keep a page silent until the person clicks it once. This button makes that visible: "Turn on sound" while the
 * browser blocks it, one click switches it on and plays the alert; "Sound on" afterwards (a click plays it again as a test).
 */
export function SoundButton() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const look = () => setOn(soundOn());
    look();
    const timer = window.setInterval(look, 1500); // a click anywhere on the page can switch sound on too
    return () => window.clearInterval(timer);
  }, []);
  return <button type="button" className={`sound-toggle${on ? ' is-on' : ''}`} onClick={() => { void enableSound().then(setOn); }}
    title={on ? 'Sound is on for new orders and notifications. Click to hear the alert.' : 'Your browser keeps this page silent until you allow sound.'}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4Z" />{on ? <><path d="M16 9a4 4 0 0 1 0 6" /><path d="M18.5 6.5a8 8 0 0 1 0 11" /></> : <path d="m16 9 5 6m0-6-5 6" />}</svg>
    <span>{on ? 'Sound on' : 'Turn on sound'}</span>
  </button>;
}
