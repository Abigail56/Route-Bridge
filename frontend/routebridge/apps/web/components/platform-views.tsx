'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  friendlyMessage,
  type ApiClient, type Company, type HealthItem, type Person, type PlatformAdminRow, type PlatformAuditRow, type SystemHealth,
} from '../lib/api';

const TABS = ['Companies', 'People', 'Administrators', 'System health', 'Audit trail'] as const;
type Tab = (typeof TABS)[number];
const ROLES = ['tenant_owner', 'tenant_admin', 'dispatcher', 'operations_manager', 'finance', 'merchant_user', 'partner_operator', 'read_only', 'driver'];
const label = (value: string) => value.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
const field = { padding: '10px 12px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'inherit', font: 'inherit' } as const;
const when = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

function useLoad<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const reload = useCallback(async () => {
    setLoading(true);
    try { setData(await loader()); setError(''); } catch (exc) { setError(friendlyMessage(exc)); } finally { setLoading(false); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

function Problem({ message }: { message: string }) {
  return message ? <p role="alert" className="low-confidence">{message}</p> : null;
}

/** The console for RouteBridge staff: every company, every person, the administrators, system health and the audit trail. */
export function PlatformConsole({ api, myId }: { api: ApiClient; myId?: string | null }) {
  const [tab, setTab] = useState<Tab>('Companies');
  return <section aria-label="Platform console">
    <p className="muted" style={{ marginTop: 0 }}>You are signed in as a RouteBridge platform administrator. This area manages every company on the platform. It shows counts and ownership, not a company&apos;s orders or customers.</p>
    <div className="segmented" style={{ marginBottom: 18, display: 'inline-flex', flexWrap: 'wrap' }}>
      {TABS.map((t) => <button key={t} className={tab === t ? 'selected' : ''} onClick={() => setTab(t)}>{t}</button>)}
    </div>
    {tab === 'Companies' && <Companies api={api} />}
    {tab === 'People' && <People api={api} myId={myId} />}
    {tab === 'Administrators' && <Administrators api={api} myId={myId} />}
    {tab === 'System health' && <Health api={api} />}
    {tab === 'Audit trail' && <AuditTrail api={api} />}
  </section>;
}

/** Small dialog to rename a workspace; `save` does the API call so platform admins and workspace owners can share it. */
export function RenameDialog({ current, save, close, done }: { current: string; save: (name: string) => Promise<unknown>; close: () => void; done: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get('name') ?? '').trim();
    if (name.length < 2) { setError('Enter a name of at least 2 characters.'); return; }
    setBusy(true); setError('');
    try { await save(name); done(); } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); }
  }
  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={(event) => event.stopPropagation()}>
    <button className="close" onClick={close} aria-label="Close">×</button>
    <h2>Rename workspace</h2>
    <p className="muted">The new name shows in the sidebar, reports and the Platform console. Existing orders and people are not affected.</p>
    <form onSubmit={submit} style={{ display: 'grid', gap: 12 }}>
      <input name="name" defaultValue={current} required minLength={2} maxLength={200} autoFocus aria-label="Workspace name" style={field} />
      <Problem message={error} />
      <div className="drawer-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button type="submit" className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Save name'}</button></div>
    </form>
  </aside></div>;
}

function Companies({ api }: { api: ApiClient }) {
  const { data, error, loading, reload } = useLoad(() => api.platform.companies(), [api]);
  const [busy, setBusy] = useState('');
  const [problem, setProblem] = useState('');
  const [ownerFor, setOwnerFor] = useState<Company | null>(null);
  const [renameFor, setRenameFor] = useState<Company | null>(null);

  async function toggle(company: Company) {
    const next = company.status === 'active' ? 'suspended' : 'active';
    if (next === 'suspended' && !window.confirm(`Suspend ${company.name}? Everyone in this company will be locked out until you reactivate it.`)) return;
    setBusy(company.tenant_id); setProblem('');
    try { await api.platform.setCompanyStatus(company.tenant_id, next); await reload(); } catch (exc) { setProblem(friendlyMessage(exc)); } finally { setBusy(''); }
  }

  return <div className="card job-table">
    <div className="table-toolbar"><div className="table-title"><b>{data?.length ?? 0} companies</b><span>{loading ? 'Loading…' : ''}</span></div></div>
    <Problem message={error || problem} />
    <div className="table-scroll"><table><thead><tr><th>COMPANY</th><th>STATUS</th><th>OWNER</th><th>PEOPLE</th><th>DRIVERS</th><th>ORDERS</th><th /></tr></thead><tbody>
      {!loading && !data?.length && <tr><td colSpan={7} className="muted">No companies yet. They appear here as soon as someone creates a workspace.</td></tr>}
      {data?.map((c) => <tr key={c.tenant_id} style={{ cursor: 'default' }}>
        <td><b>{c.name}</b><small>Created {when(c.created_at)}</small></td>
        <td><span className={`status ${c.status === 'active' ? 'status-green' : 'status-red'}`}><i />{c.status === 'active' ? 'Active' : 'Suspended'}</span></td>
        <td>{c.owners.length ? c.owners.join(', ') : <span className="unassigned">No owner</span>}</td>
        <td>{c.members}</td><td>{c.drivers}</td><td>{c.orders}</td>
        <td style={{ display: 'flex', gap: 8 }}>
          <button className="button secondary" onClick={() => setRenameFor(c)}>Rename</button>
          <button className="button secondary" onClick={() => setOwnerFor(c)}>Set owner</button>
          <button className="button secondary" disabled={busy === c.tenant_id} onClick={() => toggle(c)}>{c.status === 'active' ? 'Suspend' : 'Reactivate'}</button>
        </td>
      </tr>)}
    </tbody></table></div>
    {renameFor && <RenameDialog current={renameFor.name} save={(name) => api.platform.renameCompany(renameFor.tenant_id, name)} close={() => setRenameFor(null)} done={() => { setRenameFor(null); reload(); }} />}
    {ownerFor && <OwnerDialog api={api} company={ownerFor} close={() => setOwnerFor(null)} done={() => { setOwnerFor(null); reload(); }} />}
  </div>;
}

function OwnerDialog({ api, company, close, done }: { api: ApiClient; company: Company; close: () => void; done: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try {
      await api.platform.assignOwner(company.tenant_id, {
        clerk_user_id: String(form.get('id')).trim(), email: String(form.get('email') || '') || undefined,
        full_name: String(form.get('name') || '') || undefined, replace_existing: form.get('replace') === 'on',
      });
      done();
    } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); }
  }
  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={(event) => event.stopPropagation()}>
    <button className="close" onClick={close} aria-label="Close">×</button>
    <h2>Set owner of {company.name}</h2>
    <p className="muted">Ask the person to sign up, then paste the user id shown on their Welcome screen.</p>
    <form onSubmit={submit} style={{ display: 'grid', gap: 12 }}>
      <input name="id" required placeholder="Clerk user id (user_…)" aria-label="Clerk user id" style={field} />
      <input name="name" placeholder="Full name (optional)" aria-label="Full name" style={field} />
      <input name="email" type="email" placeholder="Email (optional)" aria-label="Email" style={field} />
      <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}><input type="checkbox" name="replace" />Make the current owner(s) an admin instead</label>
      <Problem message={error} />
      <div className="drawer-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button type="submit" className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Make owner'}</button></div>
    </form>
  </aside></div>;
}

function People({ api, myId }: { api: ApiClient; myId?: string | null }) {
  const [q, setQ] = useState('');
  const [term, setTerm] = useState('');
  const { data, error, loading, reload } = useLoad(() => api.platform.people(term), [api, term]);
  const companies = useLoad(() => api.platform.companies(), [api]);
  const [problem, setProblem] = useState('');
  const [addFor, setAddFor] = useState<Person | null>(null);

  async function toggle(person: Person) {
    const next = person.status === 'active' ? 'inactive' : 'active';
    if (next === 'inactive' && !window.confirm(`Deactivate ${person.email ?? person.clerk_user_id}? They will be locked out everywhere.`)) return;
    setProblem('');
    try { await api.platform.setPersonStatus(person.clerk_user_id, next); await reload(); } catch (exc) { setProblem(friendlyMessage(exc)); }
  }

  return <div className="card job-table">
    <form className="table-toolbar" onSubmit={(event) => { event.preventDefault(); setTerm(q); }}>
      <input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search by email, name or user id" aria-label="Search people" style={{ ...field, flex: 1, maxWidth: 380 }} />
      <button className="button primary" type="submit">Search</button>
    </form>
    <Problem message={error || problem} />
    <div className="table-scroll"><table><thead><tr><th>PERSON</th><th>STATUS</th><th>WORKSPACES</th><th /></tr></thead><tbody>
      {loading && !data && <tr aria-hidden="true"><td colSpan={4}><div className="skeleton" /></td></tr>}
      {!loading && !data?.length && <tr><td colSpan={4} className="muted">{term ? 'Nobody matches that search.' : 'No one has signed in yet.'}</td></tr>}
      {data?.map((p) => <tr key={p.clerk_user_id} style={{ cursor: 'default' }}>
        <td><b>{p.full_name ?? p.email ?? p.clerk_user_id}{p.is_platform_admin && <span className="status status-blue" style={{ marginLeft: 8 }}>RouteBridge admin</span>}</b><small style={{ maxWidth: 'none' }}>{p.email ? `${p.email} · ` : ''}{p.clerk_user_id}</small></td>
        <td><span className={`status ${p.status === 'active' ? 'status-green' : 'status-neutral'}`}><i />{p.status === 'active' ? 'Active' : 'Deactivated'}</span></td>
        <td>{p.workspaces.length ? p.workspaces.map((w) => <div key={w.tenant_id}>{w.tenant_name} <small style={{ display: 'inline' }}>· {label(w.role)}{w.status !== 'active' ? ' (inactive)' : ''}</small></div>) : <span className="unassigned">None</span>}</td>
        <td style={{ display: 'flex', gap: 8 }}>
          <button className="button secondary" onClick={() => setAddFor(p)}>Add to company</button>
          <button className="button secondary" disabled={p.clerk_user_id === myId} onClick={() => toggle(p)}>{p.status === 'active' ? 'Deactivate' : 'Reactivate'}</button>
        </td>
      </tr>)}
    </tbody></table></div>
    {addFor && <AddToCompany api={api} person={addFor} companies={companies.data ?? []} close={() => setAddFor(null)} done={() => { setAddFor(null); reload(); }} />}
  </div>;
}

function AddToCompany({ api, person, companies, close, done }: { api: ApiClient; person: Person; companies: Company[]; close: () => void; done: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true); setError('');
    try { await api.platform.addPerson(String(form.get('tenant')), { clerk_user_id: person.clerk_user_id, role: String(form.get('role')) }); done(); } catch (exc) { setError(friendlyMessage(exc)); setBusy(false); }
  }
  return <div className="drawer-backdrop" onClick={close}><aside className="drawer" onClick={(event) => event.stopPropagation()}>
    <button className="close" onClick={close} aria-label="Close">×</button>
    <h2>Add to a company</h2>
    <p className="muted">{person.email ?? person.clerk_user_id}</p>
    <form onSubmit={submit} style={{ display: 'grid', gap: 12 }}>
      <select name="tenant" required defaultValue="" style={field} aria-label="Company"><option value="" disabled>Choose a company</option>{companies.map((c) => <option key={c.tenant_id} value={c.tenant_id}>{c.name}</option>)}</select>
      <select name="role" defaultValue="dispatcher" style={field} aria-label="Role">{ROLES.map((r) => <option key={r} value={r}>{label(r)}</option>)}</select>
      <Problem message={error} />
      <div className="drawer-actions"><button type="button" className="button secondary" onClick={close}>Cancel</button><button type="submit" className="button primary" disabled={busy}>{busy ? 'Adding…' : 'Add'}</button></div>
    </form>
  </aside></div>;
}

function Administrators({ api, myId }: { api: ApiClient; myId?: string | null }) {
  const { data, error, loading, setData } = useLoad(() => api.platform.admins(), [api]);
  const [problem, setProblem] = useState('');
  const [busy, setBusy] = useState(false);

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true); setProblem('');
    try {
      setData(await api.platform.addAdmin({ clerk_user_id: String(form.get('id')).trim(), email: String(form.get('email') || '') || undefined }));
      formEl.reset();
    } catch (exc) { setProblem(friendlyMessage(exc)); } finally { setBusy(false); }
  }
  async function remove(row: PlatformAdminRow) {
    if (!window.confirm(`Remove ${row.email ?? row.clerk_user_id} as a RouteBridge administrator?`)) return;
    setProblem('');
    try { setData(await api.platform.removeAdmin(row.clerk_user_id)); } catch (exc) { setProblem(friendlyMessage(exc)); }
  }

  return <div className="card job-table">
    <form className="table-toolbar" onSubmit={add} style={{ flexWrap: 'wrap', gap: 8 }}>
      <input name="id" required placeholder="Clerk user id (user_…)" aria-label="Clerk user id" style={{ ...field, flex: 1, minWidth: 220 }} />
      <input name="email" type="email" placeholder="Email (optional)" aria-label="Email" style={{ ...field, flex: 1, minWidth: 200 }} />
      <button className="button primary" type="submit" disabled={busy}>{busy ? 'Adding…' : 'Add administrator'}</button>
    </form>
    <Problem message={error || problem} />
    <div className="table-scroll"><table><thead><tr><th>ADMINISTRATOR</th><th>MANAGED IN</th><th>ADDED</th><th /></tr></thead><tbody>
      {loading && !data && <tr aria-hidden="true"><td colSpan={4}><div className="skeleton" /></td></tr>}
      {data?.map((a) => <tr key={a.clerk_user_id} style={{ cursor: 'default' }}>
        <td><b>{a.full_name ?? a.email ?? a.clerk_user_id}{a.clerk_user_id === myId && <span className="status status-green" style={{ marginLeft: 8 }}>You</span>}</b><small style={{ maxWidth: 'none' }}>{a.email ? `${a.email} · ` : ''}{a.clerk_user_id}</small></td>
        <td>{a.source === 'database' ? 'This screen' : 'Server settings'}</td>
        <td>{a.created_at ? when(a.created_at) : 'Set at install'}{a.added_by && <small style={{ maxWidth: 'none' }}>by {a.added_by}</small>}</td>
        <td>{a.source === 'database' ? <button className="button secondary" onClick={() => remove(a)}>Remove</button> : <small style={{ maxWidth: 220, whiteSpace: 'normal' }}>Remove in the server settings</small>}</td>
      </tr>)}
    </tbody></table></div>
    <p className="muted" style={{ padding: '0 18px 16px' }}>There must always be at least one administrator. Every change here is written to the audit trail.</p>
  </div>;
}

const dot: Record<HealthItem['status'], string> = { ok: 'status-green', warning: 'status-amber', down: 'status-red', off: 'status-neutral' };
const word: Record<HealthItem['status'], string> = { ok: 'Healthy', warning: 'Needs attention', down: 'Down', off: 'Off' };

function Health({ api }: { api: ApiClient }) {
  const { data, error, loading, reload } = useLoad<SystemHealth>(() => api.platform.health(), [api]);
  const totals: [string, string][] = data ? [['Companies', 'workspaces'], ['Suspended', 'suspended_workspaces'], ['People', 'people'], ['Drivers', 'drivers'], ['Orders', 'orders']] : [];
  return <div>
    <div className="table-toolbar" style={{ padding: '0 0 14px' }}><div className="table-title"><b>System health</b><span>{data ? `Checked ${when(data.checked_at)}` : loading ? 'Checking…' : ''}</span></div><button className="button secondary" onClick={reload} disabled={loading}>Refresh</button></div>
    <Problem message={error} />
    {data && <div className="metric-grid" style={{ marginBottom: 18 }}>{totals.map(([name, key]) => <div className="card metric" key={key}><div className="metric-label">{name}</div><div className="metric-value">{data.totals[key] ?? 0}</div></div>)}</div>}
    <div className="card"><div className="table-scroll"><table style={{ minWidth: 0 }}><tbody>
      {data?.items.map((item) => <tr key={item.name} style={{ cursor: 'default' }}><td><b>{item.name}</b></td><td><span className={`status ${dot[item.status]}`}><i />{word[item.status]}</span></td><td>{item.detail}</td></tr>)}
    </tbody></table></div></div>
  </div>;
}

function AuditTrail({ api }: { api: ApiClient }) {
  const { data, error, loading } = useLoad<PlatformAuditRow[]>(() => api.platform.audit(), [api]);
  return <div className="card job-table">
    <div className="table-toolbar"><div className="table-title"><b>Latest activity</b><span>{loading ? 'Loading…' : `${data?.length ?? 0} entries`}</span></div></div>
    <Problem message={error} />
    <div className="table-scroll"><table><thead><tr><th>WHEN</th><th>WHERE</th><th>WHO</th><th>WHAT</th><th>ABOUT</th></tr></thead><tbody>
      {!loading && !data?.length && <tr><td colSpan={5} className="muted">Nothing has happened yet.</td></tr>}
      {data?.map((row, index) => <tr key={`${row.occurred_at}-${index}`} style={{ cursor: 'default' }}>
        <td>{when(row.occurred_at)}</td>
        <td><span className={`status ${row.scope === 'platform' ? 'status-blue' : 'status-neutral'}`}>{row.scope === 'platform' ? 'Platform' : 'Company'}</span></td>
        <td>{row.actor}</td><td><b>{row.action.replace(/[._]/g, ' ')}</b>{row.detail && <small style={{ maxWidth: 360 }}>{row.detail}</small>}</td><td>{row.target}</td>
      </tr>)}
    </tbody></table></div>
  </div>;
}
