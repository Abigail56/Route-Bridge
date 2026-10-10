/**
 * What a person says they will do on RouteBridge when they sign up. It only shapes the message they send to the company owner;
 * the owner still decides the real role when adding them. Kept in the browser (nothing is sent to the server).
 */
export type RoleKey = 'merchant_user' | 'dispatcher' | 'operations_manager' | 'finance' | 'tenant_admin';
export type RoleChoice = { role: RoleKey; label: string; hint: string; where: string };
export type Choice = { role: RoleKey; shop?: string };

export const ROLE_CHOICES: RoleChoice[] = [
  { role: 'merchant_user', label: 'I run a shop (merchant)', hint: 'Send parcels to customers and follow them here.', where: 'Settings, then Merchants' },
  { role: 'dispatcher', label: 'Dispatcher', hint: 'Create orders and give them to riders.', where: 'Settings, then Members & roles' },
  { role: 'operations_manager', label: 'Operations manager', hint: 'Run the day: orders, riders, problems and claims.', where: 'Settings, then Members & roles' },
  { role: 'finance', label: 'Finance', hint: 'Cash, statements and payouts.', where: 'Settings, then Members & roles' },
  { role: 'tenant_admin', label: 'Admin', hint: 'Manage people, zones and settings.', where: 'Settings, then Members & roles' },
];

const KEY = 'rb_requested_role';

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function defaultStore(): Store | null {
  try { return typeof window === 'undefined' ? null : window.localStorage; } catch { return null; }
}

export const isRoleKey = (value: unknown): value is RoleKey => ROLE_CHOICES.some((choice) => choice.role === value);
export const roleInfo = (role: RoleKey): RoleChoice => ROLE_CHOICES.find((choice) => choice.role === role) ?? ROLE_CHOICES[0];

export function loadChoice(store: Store | null = defaultStore()): Choice | null {
  try {
    const raw = store?.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { role?: unknown; shop?: unknown };
    if (!isRoleKey(parsed.role)) return null;
    const shop = typeof parsed.shop === 'string' ? parsed.shop.trim().slice(0, 120) : '';
    return { role: parsed.role, ...(shop ? { shop } : {}) };
  } catch { return null; }
}

export function saveChoice(choice: Choice | null, store: Store | null = defaultStore()): void {
  try {
    if (!store) return;
    if (!choice) { store.removeItem(KEY); return; }
    const shop = (choice.shop ?? '').trim().slice(0, 120);
    store.setItem(KEY, JSON.stringify({ role: choice.role, ...(shop ? { shop } : {}) }));
  } catch { /* storage can be blocked (private window); the choice just is not remembered */ }
}

/** What to call the id: a shop gets a "shop sign-up id", everybody else a "user id". It is the same sign-in id either way. */
export const idLabel = (role: RoleKey | null | undefined): string => (role === 'merchant_user' ? 'Shop sign-up ID' : 'User ID');

/** The ready-to-send message: who they are, what they will do, and the id the owner must paste. */
export function buildMessage(input: { subject: string; email?: string | null; choice: Choice | null }): string {
  const { subject, email, choice } = input;
  const who = email ? ` (${email})` : '';
  if (!choice) return `Hello, please add me to RouteBridge. My user id is ${subject}${who}.`;
  const info = roleInfo(choice.role);
  if (choice.role === 'merchant_user') {
    const shop = choice.shop ? ` called ${choice.shop}` : '';
    return `Hello, please add my shop${shop} to RouteBridge. My shop sign-up id is ${subject}${who}. In ${info.where}, add the shop with this id.`;
  }
  return `Hello, please add me to RouteBridge as ${info.label}. My user id is ${subject}${who}. In ${info.where}, add me with this id.`;
}
