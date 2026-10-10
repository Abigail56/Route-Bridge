'use client';

import { useEffect } from 'react';

export type Toast = { id: string; text: string; tone: 'info' | 'good' | 'warn' };

function ToastItem({ toast, dismiss }: { toast: Toast; dismiss: (id: string) => void }) {
  useEffect(() => { const timer = setTimeout(() => dismiss(toast.id), 9000); return () => clearTimeout(timer); }, [toast.id, dismiss]);
  return <div className={`rb-toast rb-toast-${toast.tone}`} role="status">
    <span className="rb-toast-dot" aria-hidden="true" />
    <span className="rb-toast-text">{toast.text}</span>
    <button type="button" className="rb-toast-close" onClick={() => dismiss(toast.id)} aria-label="Dismiss">×</button>
  </div>;
}

/** Small alerts that slide in when an order changes status, so the shop never has to refresh to find out. */
export function StatusToasts({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: string) => void }) {
  if (!toasts.length) return null;
  return <div className="rb-toasts" aria-live="polite">{toasts.map((toast) => <ToastItem key={toast.id} toast={toast} dismiss={dismiss} />)}</div>;
}
