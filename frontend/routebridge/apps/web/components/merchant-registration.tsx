'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { friendlyMessage, type ApiClient, type MerchantProfile, type PortalMe, type ProfileInput } from '../lib/api';
import { callLink } from '../lib/phone-links';

const field = { padding: '12px 14px', borderRadius: 12, border: '1.5px solid var(--line)', background: 'transparent', color: 'inherit', font: 'inherit', width: '100%', boxSizing: 'border-box' } as const;
const BANKS = ['Access Bank', 'Citibank', 'Ecobank', 'Fidelity Bank', 'First Bank', 'FCMB', 'GTBank', 'Keystone Bank', 'Kuda', 'Moniepoint', 'OPay', 'PalmPay', 'Polaris Bank', 'Stanbic IBTC', 'Sterling Bank', 'UBA', 'Union Bank', 'Wema Bank', 'Zenith Bank'];

const place = (p: Pick<MerchantProfile, 'address_line' | 'landmark' | 'city' | 'state'>) => [p.address_line, p.landmark, p.city, p.state].filter(Boolean).join(', ');

/** The shop's registration: phone, address and the bank account it is paid into. Required before the shop can create its first order. */
export function RegistrationForm({ api, tenantId, initial, onSaved, autoFocus }: { api: ApiClient; tenantId: string; initial: MerchantProfile | null; onSaved: () => void; autoFocus?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const get = (name: string) => String(form.get(name) ?? '').trim();
    const input: ProfileInput = {
      contact_phone: get('contact_phone'), contact_email: get('contact_email'), contact_person: get('contact_person') || undefined,
      address_line: get('address_line'), landmark: get('landmark') || undefined, city: get('city'), state: get('state'),
      bank_name: get('bank_name'), account_number: get('account_number'), account_name: get('account_name'),
    };
    setBusy(true); setError('');
    try { await api.portal.saveProfile(tenantId, input); onSaved(); } catch (exc) { setError(friendlyMessage(exc)); } finally { setBusy(false); }
  }
  const text = (label: string, name: string, value: string | null | undefined, extra: Record<string, unknown> = {}) => <label style={{ display: 'grid', gap: 6, flex: '1 1 240px' }}><span className="eyebrow">{label}</span><input name={name} defaultValue={value ?? ''} style={field} {...extra} /></label>;
  return <form onSubmit={save} style={{ display: 'grid', gap: 14 }}>
    <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'grid', gap: 12 }}><legend className="eyebrow" style={{ marginBottom: 8 }}>ABOUT YOUR SHOP</legend>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {text('Phone number', 'contact_phone', initial?.contact_phone, { type: 'tel', inputMode: 'tel', required: true, minLength: 7, maxLength: 30, placeholder: '+234 801 234 5678', autoFocus })}
        {text('Email for order alerts (optional)', 'contact_email', initial?.contact_email, { type: 'email', maxLength: 320, placeholder: 'shop@example.com' })}
        {text('Contact person (optional)', 'contact_person', initial?.contact_person, { maxLength: 200, placeholder: 'Who should the rider ask for?' })}
      </div>
    </fieldset>
    <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'grid', gap: 12 }}><legend className="eyebrow" style={{ marginBottom: 8 }}>WHERE RIDERS COLLECT PARCELS</legend>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {text('Street address', 'address_line', initial?.address_line, { required: true, minLength: 3, maxLength: 300, placeholder: '12 Allen Avenue' })}
        {text('Landmark (optional)', 'landmark', initial?.landmark, { maxLength: 300, placeholder: 'Opposite the bank' })}
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {text('City or town', 'city', initial?.city, { required: true, minLength: 2, maxLength: 120, placeholder: 'Ikeja' })}
        {text('State', 'state', initial?.state, { required: true, minLength: 2, maxLength: 120, placeholder: 'Lagos' })}
      </div>
    </fieldset>
    <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'grid', gap: 12 }}><legend className="eyebrow" style={{ marginBottom: 8 }}>THE BANK ACCOUNT YOU ARE PAID INTO</legend>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {text('Bank', 'bank_name', initial?.bank_name, { required: true, minLength: 2, maxLength: 120, list: 'rb-banks', placeholder: 'Start typing your bank' })}
        {text('Account number', 'account_number', initial?.account_number, { required: true, inputMode: 'numeric', pattern: '[0-9 \\-]{10,16}', minLength: 10, maxLength: 16, placeholder: '10 digits' })}
        {text('Account name', 'account_name', initial?.account_name, { required: true, minLength: 2, maxLength: 200, placeholder: 'Exactly as the bank has it' })}
      </div>
      <datalist id="rb-banks">{BANKS.map((bank) => <option key={bank} value={bank} />)}</datalist>
      <small className="muted">Only the company you deliver for can see your bank details. Riders never do.</small>
    </fieldset>
    {error && <p role="alert" className="low-confidence" style={{ margin: 0 }}>{error}</p>}
    <div><button className="button primary" type="submit" disabled={busy}>{busy ? 'Saving…' : initial?.complete ? 'Save changes' : 'Finish registration'}</button></div>
  </form>;
}

/** Overview card for the shop: the registration form until it is complete, then a short summary with an edit button. */
export function RegistrationCard({ api, tenantId, me, onChanged }: { api: ApiClient; tenantId: string; me: PortalMe; onChanged: () => void }) {
  const [profile, setProfile] = useState<MerchantProfile | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState('');
  const refresh = () => api.portal.profile(tenantId).then((p) => { setProfile(p); setError(''); }).catch((exc) => setError(friendlyMessage(exc)));
  useEffect(() => { refresh(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, tenantId, me.profile_complete]);
  const done = me.profile_complete === true;
  return <section className="card" aria-label="Your shop details" style={{ padding: 18, marginBottom: 20, borderLeft: `5px solid ${done ? '#16a34a' : '#ff7a29'}` }}>
    <b>{done ? 'Your shop details' : 'Finish registering your shop'}</b>
    {!done && <p className="muted" style={{ margin: '4px 0 14px' }}>Give us your phone number, your address and the bank account you are paid into. You can send your first order as soon as this is saved.</p>}
    {error && <p role="alert" className="low-confidence">{error}</p>}
    {(!done || editing) && <div style={{ marginTop: done ? 12 : 0 }}><RegistrationForm api={api} tenantId={tenantId} initial={profile} autoFocus={!done} onSaved={() => { setEditing(false); refresh(); onChanged(); }} /></div>}
    {done && !editing && profile && <>
      <p className="muted" style={{ margin: '4px 0 10px' }}>{place(profile)}<br />{profile.bank_name} · {profile.account_name} · account ending {profile.account_number?.slice(-4)}</p>
      <button className="button secondary" onClick={() => setEditing(true)}>Edit details</button>
    </>}
  </section>;
}

/** Settings for the company: every shop's registration at a glance. Bank details show only to the roles that handle money. */
export function MerchantDetailsPanel({ api, tenantId, refreshKey = 0 }: { api: ApiClient; tenantId: string; refreshKey?: number }) {
  const [rows, setRows] = useState<MerchantProfile[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api.getMerchantProfiles(tenantId).then((list) => { setRows(list); setError(''); }).catch((exc) => setError(friendlyMessage(exc))); }, [api, tenantId, refreshKey]);
  if (error) return <p role="alert" className="low-confidence">{error}</p>;
  if (!rows?.length) return null;
  return <div style={{ marginTop: 20 }}>
    <b>Shop details</b>
    <p className="muted" style={{ margin: '4px 0 12px' }}>What each shop gave when it registered. A shop that has not finished cannot create orders yet.</p>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
      {rows.map((row) => <div key={row.merchant_id} className="drawer-block" style={{ borderLeft: `4px solid ${row.complete ? '#16a34a' : '#ff7a29'}`, paddingLeft: 14 }}>
        <span className="eyebrow">{row.complete ? 'REGISTERED' : 'WAITING FOR THE SHOP TO REGISTER'}</span>
        <b>{row.merchant_name}</b>
        {row.complete ? <>
          <small>{place(row)}</small>
          <small>{row.contact_person ? `${row.contact_person} · ` : ''}{row.contact_phone ? <a href={callLink(row.contact_phone)}>{row.contact_phone}</a> : 'no phone'}{row.contact_email ? ` · ${row.contact_email}` : ''}</small>
          {row.bank_visible
            ? <small><b>{row.bank_name}</b> · {row.account_name} · <span style={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace' }}>{row.account_number}</span></small>
            : <small className="muted">Bank details are visible to the owner, admins and finance only.</small>}
        </> : <small className="muted">The shop signs in with the user id you added and fills in its phone, address and bank account.</small>}
      </div>)}
    </div>
  </div>;
}
