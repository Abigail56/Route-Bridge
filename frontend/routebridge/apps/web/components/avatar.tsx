import { initialsOf } from '../lib/avatar';

/** A round picture, or the person's initials when there is none. */
export function Avatar({ name, photo, size = 40 }: { name: string; photo?: string | null; size?: number }) {
  const base = { width: size, height: size, borderRadius: '50%', flex: 'none' } as const;
  // eslint-disable-next-line @next/next/no-img-element
  if (photo) return <img src={photo} alt={`Photo of ${name}`} width={size} height={size} style={{ ...base, objectFit: 'cover' }} />;
  return <span aria-hidden="true" style={{ ...base, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'var(--accent-soft, #e6ecf8)', color: 'var(--accent-strong, #1d3a8a)', fontWeight: 700, fontSize: size * 0.38 }}>{initialsOf(name)}</span>;
}
