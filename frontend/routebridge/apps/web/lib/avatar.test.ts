import { describe, expect, it } from 'vitest';
import { dataUrlBytes, initialsOf } from './avatar';

describe('avatar helpers', () => {
  it('measures the real size of a data URL', () => {
    expect(dataUrlBytes('data:image/jpeg;base64,AAAA')).toBe(3);
    expect(dataUrlBytes('data:image/jpeg;base64,AAA=')).toBe(2);
    expect(dataUrlBytes('data:image/jpeg;base64,AA==')).toBe(1);
  });

  it('makes initials from a name', () => {
    expect(initialsOf('Ada Okafor')).toBe('AO');
    expect(initialsOf('  musa  ')).toBe('M');
    expect(initialsOf('Chinedu Emeka Obi')).toBe('CO');
    expect(initialsOf('')).toBe('?');
  });
});
