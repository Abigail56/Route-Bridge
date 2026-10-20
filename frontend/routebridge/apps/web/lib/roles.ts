/**
 * The names people see for roles. The owner of a workspace IS the Admin (one person, full control), a "driver" login is a Dispatcher
 * (the rider who sees only their own orders), and a shop's login is a Shop. Older logins keep their old role and name until the Admin changes them.
 */
const NAMES: Record<string, string> = {
  tenant_owner: 'Admin (Owner)',
  driver: 'Driver',
  merchant_user: 'Shop',
  tenant_admin: 'Admin (older login)',
  dispatcher: 'Office dispatcher (older login)',
  operations_manager: 'Operations manager (older login)',
  finance: 'Finance (older login)',
  partner_operator: 'Partner (older login)',
  read_only: 'View only (older login)',
};

export function roleName(role: string | null | undefined): string {
  if (!role) return 'Operations';
  return NAMES[role] ?? role.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
}

/** The only people the Admin adds from Members & roles. Shops are added with Add merchant. */
export const ADDABLE_ROLES = ['driver'] as const;

/** Dispatchers are either on the company's staff or contracted. Older riders may carry the old "owned" or "partner" type. */
export const FLEET_TYPES = [['staff', 'Staff'], ['contracted', 'Contracted']] as const;
export function fleetName(type: string | null | undefined): string {
  if (!type) return '';
  return { staff: 'Staff', contracted: 'Contracted', owned: 'Staff (owned)', partner: 'Partner (older)' }[type] ?? type;
}
