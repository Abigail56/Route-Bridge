/**
 * "Sign in as": Admin, Merchant or Dispatcher. It only says which door the person means to use, and it grants nothing:
 * nobody gets in unless the Admin has added their account, and what the account may do comes from the role the Admin gave it.
 * If the choice and the account's real role disagree, the console says so instead of silently showing something else.
 */
export type SignInAs = 'admin' | 'merchant' | 'dispatcher';

export const SIGN_IN_CHOICES: { key: SignInAs; label: string }[] = [
  { key: 'admin', label: 'Admin' },
  { key: 'merchant', label: 'Merchant (shop)' },
  { key: 'dispatcher', label: 'Dispatcher (rider)' },
];

const KEY = 'rb_signin_as';
type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;
const defaultStore = (): Store | null => { try { return typeof window === 'undefined' ? null : window.localStorage; } catch { return null; } };

export const isSignInAs = (value: unknown): value is SignInAs => value === 'admin' || value === 'merchant' || value === 'dispatcher';

export function loadSignInAs(store: Store | null = defaultStore()): SignInAs | null {
  try { const value = store?.getItem(KEY); return isSignInAs(value) ? value : null; } catch { return null; }
}

export function saveSignInAs(choice: SignInAs | null, store: Store | null = defaultStore()): void {
  try { if (!store) return; if (choice) store.setItem(KEY, choice); else store.removeItem(KEY); } catch { /* storage can be blocked; the choice is just not remembered */ }
}

/** Which door an account's role belongs to. Everyone who works in the console (the owner and older office roles) is on the Admin side. */
export function doorOf(role: string | null | undefined): SignInAs {
  if (role === 'merchant_user') return 'merchant';
  if (role === 'driver') return 'dispatcher';
  return 'admin';
}

const NAMES: Record<SignInAs, string> = { admin: 'an Admin', merchant: 'a Merchant', dispatcher: 'a Dispatcher' };

/** null when the choice matches the account (or nothing was chosen); otherwise a plain sentence for the person. */
export function mismatchMessage(choice: SignInAs | null, role: string | null | undefined): string | null {
  if (!choice || !role) return null;
  const actual = doorOf(role);
  return actual === choice ? null : `You chose to sign in as ${NAMES[choice]}, but this account was added by the Admin as ${NAMES[actual]}.`;
}
