'use client';

import { useEffect, useRef, useState } from 'react';
import { useAuth } from '../lib/auth';

/** The signed-in person's initial, opening their name, email and Sign out. */
export function AccountMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === 'Escape' : !box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close); };
  }, [open]);
  if (!user) return null;
  const initial = (user.name || user.email || '?').trim().charAt(0).toUpperCase();
  return <div className="account-menu" ref={box}>
    <button type="button" className="account-avatar" aria-haspopup="menu" aria-expanded={open} aria-label="Your account" onClick={() => setOpen((value) => !value)}>{initial}</button>
    {open && <div className="account-popover" role="menu">
      <div className="account-who"><b>{user.name || 'Your account'}</b>{user.email && <small>{user.email}</small>}</div>
      <button type="button" role="menuitem" onClick={() => void signOut({ redirectUrl: '/' })}>Sign out</button>
      <button type="button" role="menuitem" onClick={() => void signOut({ redirectUrl: '/', everywhere: true })}>Sign out on every device</button>
    </div>}
  </div>;
}
