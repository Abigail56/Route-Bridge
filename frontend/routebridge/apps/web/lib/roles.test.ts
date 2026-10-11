import { describe, expect, it } from 'vitest';
import { ADDABLE_ROLES, fleetName, roleName } from './roles';

describe('role names', () => {
  it('shows the owner as the Admin and the rider as a Dispatcher', () => {
    expect(roleName('tenant_owner')).toBe('Admin (Owner)');
    expect(roleName('driver')).toBe('Dispatcher');
    expect(roleName('merchant_user')).toBe('Shop');
  });
  it('keeps older roles readable and never fails on an unknown one', () => {
    expect(roleName('finance')).toContain('older');
    expect(roleName('wizard_of_oz')).toBe('Wizard of oz');
    expect(roleName(null)).toBe('Operations');
  });
  it('lets the Admin add only Dispatchers, who are Staff or Contracted', () => {
    expect([...ADDABLE_ROLES]).toEqual(['driver']);
    expect(fleetName('staff')).toBe('Staff');
    expect(fleetName('contracted')).toBe('Contracted');
    expect(fleetName('partner')).toContain('older');
    expect(fleetName(undefined)).toBe('');
  });
});
