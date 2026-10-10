'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { friendlyMessage, type ApiClient, type Merchant, type MerchantProfile, type PortalMe, type ProfileInput } from '../lib/api';
import { callLink } from '../lib/phone-links';

const field = { padding: '12px 14px', borderRadius: 12, border: '1.5px solid var(--line)', background: 'transparent', color: 'inherit', font: 'inherit', width: '100%', boxSizing: 'border-box' } as const;
const BANKS = ['Access Bank', 'Citibank', 'Ecobank', 'Fidelity Bank', 'First Bank', 'FCMB', 'GTBank', 'Keystone Bank', 'Kuda', 'Moniepoint', 'OPay', 'PalmPay', 'Polaris Bank', 'Stanbic IBTC', 'Sterling Bank', 'UBA', 'Union Bank', 'Wema Bank', 'Zenith Bank'];

const place = (p: Pick<MerchantProfile, 'address_line' | 'landmark' | 'city' | 'state'>) => [p.address_line, p.landmark, p.city, p.state].filter(Boolean).join(', ');

/** The shop's own id, made by RouteBridge the moment the owner adds the shop. Shown with a copy button. */
export function ShopId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() { try { await navigator.clipboard.writeText(id); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { setCopied(false); } }
  return <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', margin: '4px 0' }}><span className="eyebrow">SHOP ID</span><code style={{ wordBreak: 'break-all', fontSize: 12 }}>{id}</code><button type="button" className="button secondary" style={{ padding: '4px 12px', minHeight: 32 }} onClick={copy} aria-label="Copy shop ID">{copied ? 'Copied' : 'Copy'}</button></span>;
}

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
    <ShopId id={me.merchant_id} />
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
export function MerchantDetailsPanel({ api, tenantId, refreshKey = 0, canRemove = false, onRemove }: { api: ApiClient; tenantId: string; refreshKey?: number; canRemove?: boolean; onRemove?: (merchantId: string) => Promise<void> }) {
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
        <ShopId id={row.merchant_id} />
        {row.complete ? <>
          <small>{place(row)}</small>
          <small>{row.contact_person ? `${row.contact_person} · ` : ''}{row.contact_phone ? <a href={callLink(row.contact_phone)}>{row.contact_phone}</a> : 'no phone'}{row.contact_email ? ` · ${row.contact_email}` : ''}</small>
          {row.bank_visible
            ? <small><b>{row.bank_name}</b> · {row.account_name} · <span style={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace' }}>{row.account_number}</span></small>
            : <small className="muted">Bank details are visible to the owner, admins and finance only.</small>}
        </> : <small className="muted">The shop signs in with the user id you added and fills in its phone, address and bank account.</small>}
        {canRemove && onRemove && <RemoveShop name={row.merchant_name} onConfirm={() => onRemove(row.merchant_id)} />}
      </div>)}
    </div>
  </div>;
}

/** Remove with a question first, so a stray tap on a phone cannot remove a shop. */
function RemoveShop({ name, onConfirm }: { name: string; onConfirm: () => Promise<void> }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!asking) return <span><button type="button" className="button secondary" style={{ minHeight: 44, marginTop: 6 }} onClick={() => setAsking(true)} aria-label={`Remove ${name}`}>Remove</button></span>;
  return <span role="alert" style={{ display: 'grid', gap: 8, marginTop: 6 }}>
    <span>Remove <span style={{ fontWeight: 700 }}>{name}</span>? Its login stops working and no new orders can be created for it. Past orders and statements are kept.</span>
    <span style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
      <button type="button" className="button primary" style={{ minHeight: 44 }} disabled={busy} onClick={async () => { setBusy(true); try { await onConfirm(); } finally { setBusy(false); setAsking(false); } }}>{busy ? 'Removing…' : 'Yes, remove'}</button>
      <button type="button" className="button secondary" style={{ minHeight: 44 }} disabled={busy} onClick={() => setAsking(false)}>Keep</button>
    </span>
  </span>;
}

/** Shops the owner removed. The owner can bring one back with its history and its login. */
export function RemovedShops({ api, tenantId, canRestore, refreshKey = 0, onRestored }: { api: ApiClient; tenantId: string; canRestore: boolean; refreshKey?: number; onRestored: () => void }) {
  const [rows, setRows] = useState<Merchant[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [note, setNote] = useState('');
  const load = () => api.getRemovedMerchants(tenantId).then((list) => { setRows(list); setError(''); }).catch((exc) => setError(friendlyMessage(exc)));
  useEffect(() => { load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, tenantId, refreshKey]);
  async function restore(shop: Merchant) {
    setBusy(shop.id); setError(''); setNote('');
    try {
      const result = await api.restoreMerchant(tenantId, shop.id);
      setNote(`${shop.name} is back${result.logins_switched_on ? ' and its login works again' : '. It has no login now: add one in Members & roles'}.`);
      await load(); onRestored();
    } catch (exc) { setError(friendlyMessage(exc)); } finally { setBusy(''); }
  }
  if (error && !rows?.length) return <p role="alert" className="low-confidence">{error}</p>;
  if (!rows?.length && !note) return null;
  return <div style={{ marginTop: 20 }}>
    {!!rows?.length && <>
      <b>Removed shops</b>
      <p className="muted" style={{ margin: '4px 0 12px' }}>These shops cannot sign in or get new orders. Restoring one brings back its history and its login.</p>
    </>}
    {note && <p role="status" className="notice" style={{ marginTop: 0 }}>{note}</p>}
    {error && <p role="alert" className="low-confidence">{error}</p>}
    <div style={{ display: 'grid', gap: 10 }}>
      {rows?.map((shop) => <div key={shop.id} className="drawer-block" style={{ display: 'flex', gap: 12, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', paddingLeft: 14, borderLeft: '4px solid #94a3b8' }}>
        <span><b>{shop.name}</b><ShopId id={shop.id} /></span>
        {canRestore && <button type="button" className="button primary" style={{ minHeight: 44 }} disabled={busy !== ''} onClick={() => restore(shop)} aria-label={`Restore ${shop.name}`}>{busy === shop.id ? 'Restoring…' : 'Restore'}</button>}
      </div>)}
    </div>
  </div>;
}
