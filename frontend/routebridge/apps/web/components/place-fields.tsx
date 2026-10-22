'use client';

import { useMemo } from 'react';
import { NIGERIA_STATES, countryOptions } from '../lib/places';

export type Place = { phone: string; country: string; state: string; region: string };

/** Phone, country, state and region: on the sign-up form and on the "your details" step after a Google sign-up. */
export function PlaceFields({ value, onChange, inputStyle }: { value: Place; onChange: (next: Place) => void; inputStyle?: React.CSSProperties }) {
  const countries = useMemo(() => countryOptions(), []);
  const set = (key: keyof Place) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    onChange({ ...value, [key]: event.target.value, ...(key === 'country' ? { state: '' } : {}) });
  const nigeria = value.country === 'NG';
  return <>
    <label>Phone number<input type="tel" value={value.phone} onChange={set('phone')} required minLength={7} maxLength={30} inputMode="tel" autoComplete="tel" placeholder="+234 801 234 5678" style={inputStyle} /></label>
    <label>Country<select value={value.country} onChange={set('country')} required autoComplete="country" style={inputStyle}>
      {countries.map((country) => <option key={country.code} value={country.code}>{country.name}</option>)}
    </select></label>
    <label>State{nigeria
      ? <select value={value.state} onChange={set('state')} required autoComplete="address-level1" style={inputStyle}>
          <option value="">Choose your state…</option>
          {NIGERIA_STATES.map((state) => <option key={state} value={state}>{state}</option>)}
        </select>
      : <input value={value.state} onChange={set('state')} required minLength={2} maxLength={100} autoComplete="address-level1" placeholder="State, province or county" style={inputStyle} />}
    </label>
    <label>Region<input value={value.region} onChange={set('region')} required minLength={2} maxLength={120} autoComplete="address-level2" placeholder={nigeria ? 'City or LGA, e.g. Ikeja' : 'City or area'} style={inputStyle} /></label>
  </>;
}

export const EMPTY_PLACE: Place = { phone: '', country: 'NG', state: '', region: '' };
