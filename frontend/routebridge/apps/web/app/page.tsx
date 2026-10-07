'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { LiveStreamStatus } from '../components/live-stream-status';
import { ThemeToggle } from '../components/theme-toggle';
import { AccountMenu } from '../components/account-menu';
import { FirstRunScreen, SetupChecklist } from '../components/onboarding';
import { PlatformConsole } from '../components/platform-views';
import { MerchantPortal } from '../components/merchant-portal';
import { LiveTracking, MiniLiveMap } from '../components/tracking-views';
import { ClaimsPanel, DispatchBatches, ExceptionsPanel, FinanceTools, InsightsPanel, SettingsPanels } from '../components/admin-views';
import { DriversView, JobDrawer, NewOrderModal, ReconciliationView } from '../components/workspace-views';
import { createApiClient, friendlyMessage, type ApiClient, type ReconciliationItem } from '../lib/api';
import { useGetToken } from '../lib/auth-token';
import { toJob, toAmount, type Job, type Status } from '../lib/jobs';
import { useEventStream } from '../lib/use-event-stream';
import { useTenant } from '../lib/use-tenant';

const labels: Record<Status, string> = { pending: 'Unassigned', assigned: 'Assigned', en_route: 'En route', arrived: 'Arrived', delivered: 'Delivered', exception: 'Exception' };
const classes: Record<Status, string> = { pending: 'status-neutral', assigned: 'status-blue', en_route: 'status-blue', arrived: 'status-amber', delivered: 'status-green', exception: 'status-red' };
const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });

function initials(name?: string) { return name ? name.split(' ').map((part) => part[0]).join('') : ''; }
function Icon({ type }: { type: 'overview' | 'dispatch' | 'orders' | 'drivers' | 'finance' | 'settings' | 'platform' | 'map' }) {
  const path = { map: 'M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 7zM9 4v13M15 7v12.5', platform: 'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6zM9 12l2 2 4-4', overview: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z', dispatch: 'M3 6h11v10H3zM14 10h4l3 3v3h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z', orders: 'M4 7 12 3l8 4-8 4-8-4Zm0 0v10l8 4 8-4V7M12 11v10', drivers: 'M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-3 4v1M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM20 20v-1a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75', finance: 'M4 19V5M4 19h17M8 16v-4M12 16V8M16 16v-7M20 16v-3', settings: 'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z' }[type];
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={path} /></svg>;
}

// Each console page has its own address, so links, refresh and the back button all work.
const PATHS: Record<string, string> = { Overview: '/', 'Dispatch board': '/dispatch', 'Live map': '/tracking', Orders: '/orders', Drivers: '/drivers', Reconciliation: '/reconciliation', Settings: '/settings', Platform: '/platform' };
function sectionFromPath(path: string) {
  const clean = path.replace(/\/+$/, '') || '/';
  return Object.keys(PATHS).find((label) => PATHS[label] === clean) ?? 'Overview';
}

function greetingFor(date: Date) { const h = date.getHours(); return h >= 5 && h < 12 ? 'Good morning' : h >= 12 && h < 17 ? 'Good afternoon' : 'Good evening'; }
const WELCOME_LINES = [
  'Welcome to RouteBridge, where every parcel finds its way home.',
  'Welcome to RouteBridge, where life is made easy, one doorstep at a time.',
  'Welcome to RouteBridge. Your riders, your customers and your day, all in step.',
  'Welcome to RouteBridge. Great deliveries are made of small, well-kept promises.'
];
const DAY_PROMISE = [
  'Let us get every parcel to its doorstep today.',
  'Your riders are ready when you are.',
  'A calm dispatch board makes a happy customer.',
  'Small details today, big smiles at the door.'
];
function initialsOf(text: string) { return text.split(' ').filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'RB'; }
function dayKey(date: Date) { return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`; }

function exportCsv(jobs: Job[]) {
  const escape = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`;
  const rows = [['Order', 'Customer', 'Merchant', 'Location', 'Landmark', 'Status', 'Driver', 'COD amount', 'Created'], ...jobs.map((job) => [job.order, job.customer, job.merchant, job.area, job.landmark, job.status, job.driver ?? '', job.amount, job.createdAt])];
  const url = URL.createObjectURL(new Blob([rows.map((row) => row.map(escape).join(',')).join('\r\n')],{ type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'routebridge-jobs.csv';
  link.click();
  URL.revokeObjectURL(url);
}

export default function Home() {
  const getToken = useGetToken();
  const api = useMemo(() => createApiClient(getToken), [getToken]);
  const { tenant, profile, status: tenantStatus, error: tenantError, reload: reloadTenant } = useTenant(api);
  const [settingsTab, setSettingsTab] = useState<'members' | 'merchants' | 'zones' | 'audit' | undefined>(undefined);
  const tenantId = tenant?.tenant_id;
  const isMerchant = tenant?.role === 'merchant_user';
  const [jobs, setJobs] = useState<Job[]>([]);
  const [recon, setRecon] = useState<ReconciliationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!tenantId || isMerchant) return;
    try {
      const [orders, items] = await Promise.all([api.getOrders(tenantId), api.getReconciliation(tenantId).catch(() => [] as ReconciliationItem[])]);
      setJobs(orders.map(toJob));
      setRecon(items);
      setLoadError('');
      setUpdatedAt(Date.now());
    } catch (exc) {
      setLoadError(friendlyMessage(exc));
    } finally {
      setLoading(false);
    }
  }, [api, tenantId, isMerchant]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tenantError) { setLoadError(tenantError); setLoading(false); } }, [tenantError]);

  // Refresh when the backend announces a change; coalesce bursts of events into one reload.
  const [refreshTick, setRefreshTick] = useState(0);
  useEffect(() => {
    if (!refreshTick) return;
    const timer = setTimeout(load, 400);
    return () => clearTimeout(timer);
  }, [refreshTick, load]);
  const streamState = useEventStream(isMerchant ? undefined : tenantId, getToken, () => setRefreshTick((tick) => tick + 1));

  const openRecon = useMemo(() => recon.filter((item) => item.status === 'open'), [recon]);
  const stats = useMemo(() => {
    const delivered = jobs.filter((job) => job.status === 'delivered').length;
    const exceptions = jobs.filter((job) => job.status === 'exception').length;
    const unassigned = jobs.filter((job) => job.status === 'pending').length;
    const lowConfidence = jobs.filter((job) => job.confidence === 'Low' && job.status !== 'delivered').length;
    const codInFlight = jobs.filter((job) => job.status !== 'delivered' && job.status !== 'exception').reduce((sum, job) => sum + job.amount, 0);
    const reconVariance = openRecon.reduce((sum, item) => sum + Math.abs(toAmount(item.variance_amount)), 0);
    return { delivered, exceptions, unassigned, lowConfidence, codInFlight, reconVariance };
  }, [jobs, openRecon]);

  const [section, setSectionState] = useState('Overview');
  const setSection = useCallback((label: string) => {
    const href = PATHS[label] ?? '/';
    if (window.location.pathname !== href) window.history.pushState(null, '', href);
    setSectionState(label);
    window.scrollTo(0, 0);
  }, []);
  useEffect(() => {
    const sync = () => setSectionState(sectionFromPath(window.location.pathname));
    sync();
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
  }, []);
  useEffect(() => { document.title = section === 'Overview' ? 'RouteBridge | Operations Console' : `${section} | RouteBridge`; }, [section]);
  const [filter, setFilter] = useState<'all' | Status>('all');
  const [selected, setSelected] = useState<Job | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const timer = setInterval(() => setNow(new Date()), 60_000); return () => clearInterval(timer); }, []);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [bellOpen, setBellOpen] = useState(false);
  const [justCreated, setJustCreated] = useState(false);
  const [platformOnly, setPlatformOnly] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return jobs.filter((job) => (filter === 'all' || job.status === filter) && (!needle || [job.order, job.customer, job.merchant, job.area, job.landmark, job.driver].some((value) => String(value ?? '').toLowerCase().includes(needle))));
  }, [filter, jobs, query]);
  const rows = section === 'Overview' ? filtered.slice(0, 5) : filtered;
  const baseNav = [['Overview', 'overview'], ['Dispatch board', 'dispatch'], ['Live map', 'map'], ['Orders', 'orders'], ['Drivers', 'drivers'], ['Reconciliation', 'finance'], ['Settings', 'settings']] as const;
  const nav = profile?.is_platform_admin ? [...baseNav, ['Platform', 'platform'] as const] : baseNav;
  const workspaceName = tenant?.name || 'Your workspace';
  const firstName = (profile?.name || '').trim().split(/\s+/)[0] || '';
  const roleLabel = tenant?.role ? tenant.role.replace(/_/g, ' ') : 'Operations';
  type Alert = { title: string; hint: string; target: string; filter?: Status; tone: 'amber' | 'red' | 'violet' | 'blue' };
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const alerts: Alert[] = [
    ...(stats.unassigned ? [{ title: `${plural(stats.unassigned, 'job is', 'jobs are')} waiting for a driver`, hint: 'Open the list and assign a rider.', target: 'Orders', filter: 'pending' as Status, tone: 'amber' as const }] : []),
    ...(stats.exceptions ? [{ title: `${plural(stats.exceptions, 'delivery needs', 'deliveries need')} your review`, hint: 'These failed, were returned or were cancelled.', target: 'Orders', filter: 'exception' as Status, tone: 'red' as const }] : []),
    ...(stats.lowConfidence ? [{ title: `${plural(stats.lowConfidence, 'address', 'addresses')} to confirm`, hint: 'The map position is uncertain. A rider may struggle to find it.', target: 'Orders', tone: 'violet' as const }] : []),
    ...(openRecon.length ? [{ title: `${plural(openRecon.length, 'cash item', 'cash items')} to reconcile`, hint: 'Cash collected does not yet match what was expected.', target: 'Reconciliation', tone: 'blue' as const }] : [])
  ];
  const attention = stats.exceptions + stats.lowConfidence + openRecon.length;
  const deliveredPct = jobs.length ? `${((stats.delivered / jobs.length) * 100).toFixed(1)}%` : '—';

  const goTo = (target: string, tab?: 'members' | 'merchants' | 'zones') => { setSection(target); if (tab) setSettingsTab(tab); };
  const accountMenu = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ? <AccountMenu /> : null;
  if (tenantStatus === 'loading') return <main style={{ maxWidth: 420, margin: '20vh auto', textAlign: 'center' }}>Loading your workspace…</main>;
  if (isMerchant && tenant) return <MerchantPortal api={api} tenant={tenant} firstName={firstName} accountMenu={accountMenu} />;
  // a platform administrator runs the platform; they do not create a workspace of their own, so they land on the Platform console
  if (tenantStatus === 'needs-workspace' && profile && (platformOnly || profile.is_platform_admin)) return <main className="page-wrap"><div className="page-heading"><div><div className="breadcrumb">ROUTEBRIDGE</div><h1>Platform console</h1><p>Manage every company on RouteBridge.</p></div><div className="heading-actions">{!profile.is_platform_admin && <button className="button secondary" onClick={() => setPlatformOnly(false)}>Back</button>}{accountMenu}</div></div><PlatformConsole api={api} myId={profile.subject} /></main>;
  if (tenantStatus === 'needs-workspace' && profile) return <FirstRunScreen api={api} profile={profile} onCreated={reloadTenant} accountMenu={accountMenu} onOpenPlatform={profile.is_platform_admin ? () => setPlatformOnly(true) : undefined} />;

  return <main className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark" role="img" aria-label="RouteBridge logo" /><div><strong>RouteBridge</strong><span>Operations console</span></div></div>
      <div className="workspace"><span className="eyebrow">WORKSPACE</span><div className="workspace-row"><div className="workspace-avatar">{initialsOf(workspaceName)}</div><div><b>{workspaceName}</b><small>{roleLabel}</small></div><span className="chevron">⌄</span></div></div>
      <nav className="nav">{nav.map(([label, icon]) => <a key={label} href={PATHS[label]} aria-current={section === label ? 'page' : undefined} className={section === label ? 'nav-item active' : 'nav-item'} onClick={(event) => { event.preventDefault(); setSection(label); }}><Icon type={icon} /><span>{label}</span>{label === 'Reconciliation' && openRecon.length > 0 && <em>{openRecon.length}</em>}</a>)}</nav>
      <div className="sidebar-bottom"><div className="pilot-card"><div className="pilot-dot" /><div><b>{streamState === 'live' ? 'Connected' : 'Pilot mode'}</b><small>RouteBridge · v0.1</small></div></div><div className="user-row"><div className="user-avatar">{initialsOf(workspaceName)}</div><div><b>{workspaceName}</b><small>{roleLabel}</small></div><span className="more">•••</span></div></div>
    </aside>
    <section className="content">
      <header className="topbar"><div className="mobile-brand"><div className="brand-mark" role="img" aria-label="RouteBridge logo" /><strong>RouteBridge</strong></div><div className="top-actions"><ThemeToggle /><LiveStreamStatus state={streamState} />{searchOpen && <input className="topbar-search" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Escape') { setQuery(''); setSearchOpen(false); } }} placeholder="Search orders, customers, areas…" aria-label="Search jobs" />}<button className="icon-btn" aria-label="Search" onClick={() => { if (searchOpen && query) setQuery(''); setSearchOpen(!searchOpen); if (!searchOpen && !['Overview', 'Dispatch board', 'Orders'].includes(section)) setSection('Orders'); }}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg></button><div className="popover-anchor"><button className="icon-btn notification" aria-label="Notifications" aria-expanded={bellOpen} onClick={() => setBellOpen(!bellOpen)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" /></svg><i /></button>{bellOpen && <div className="popover popover-notifications" role="menu"><div className="popover-title"><b>Notifications</b><span>{alerts.length ? `${alerts.length} need${alerts.length === 1 ? 's' : ''} your attention` : 'All clear'}</span></div>{alerts.length ? alerts.map((alert) => <button key={alert.title} role="menuitem" className={`alert-item tone-${alert.tone}`} onClick={() => { setBellOpen(false); if (alert.filter) setFilter(alert.filter); goTo(alert.target); }}><span className="alert-dot" aria-hidden="true" /><span className="alert-text"><b>{alert.title}</b><small>{alert.hint}</small></span><span className="alert-go" aria-hidden="true">›</span></button>) : <div className="alert-empty"><b>You are all caught up</b><p>Nothing needs your attention right now.</p></div>}</div>}</div>{accountMenu ?? <div className="top-avatar">{initialsOf(workspaceName)}</div>}</div></header>
      <div className="page-wrap">
        {section === 'Overview' && <section className="hero" aria-label="Welcome">
          <div className="hero-copy">
            <span className="hero-date">{now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</span>
            <h1>{greetingFor(now)}{firstName ? `, ${firstName}` : ''}</h1>
            <p className="hero-welcome">{WELCOME_LINES[now.getDate() % WELCOME_LINES.length]}</p>
            <p className="hero-sub">{jobs.length ? `${jobs.filter((job) => job.status === 'en_route' || job.status === 'arrived' || job.status === 'assigned').length} on the road and ${stats.unassigned} waiting for a driver. ${DAY_PROMISE[now.getDate() % DAY_PROMISE.length]}` : 'A fresh start. Add your first order and watch it travel from pickup to doorstep.'}</p>
            <div className="hero-actions"><button className="hero-btn solid" onClick={() => setShowNew(true)} disabled={!tenantId}>+ New order</button><button className="hero-btn ghost" onClick={() => setSection('Dispatch board')}>Open dispatch board</button><button className="hero-btn ghost" onClick={() => exportCsv(jobs)} disabled={!jobs.length}>Export report</button></div>
          </div>
          <div className="hero-art" aria-hidden="true">
            <svg viewBox="0 0 420 240"><path className="hero-route" d="M20 200 C110 70 180 210 250 120 S370 40 400 30" /><circle className="hero-dot" r="7"><animateMotion dur="9s" repeatCount="indefinite" path="M20 200 C110 70 180 210 250 120 S370 40 400 30" /></circle><circle cx="20" cy="200" r="9" className="hero-pin a" /><circle cx="250" cy="120" r="9" className="hero-pin b" /><circle cx="400" cy="30" r="11" className="hero-pin c" /></svg>
            <div className="hero-chip one"><b>{jobs.filter((job) => job.status === 'delivered').length}</b><span>delivered</span></div>
            <div className="hero-chip two"><b>{jobs.length}</b><span>deliveries in total</span></div>
          </div>
        </section>}
        <div className={section === 'Overview' ? 'page-heading is-overview' : 'page-heading'}><div><div className="breadcrumb">{workspaceName.toUpperCase()} <span>/</span> TODAY</div><h1>{section === 'Overview' ? `${greetingFor(now)}${firstName ? `, ${firstName}` : ''}` : section}</h1><p>{section === 'Overview' ? `${WELCOME_LINES[now.getDate() % WELCOME_LINES.length]} Here is what needs your attention today.` : (section === 'Platform' ? 'Run RouteBridge itself: companies, people, administrators, health and audit.' : section === 'Live map' ? 'See where every rider is and how close they are to the door.' : section === 'Drivers' ? 'Your riders. Give each one a link or QR code to sign in on their phone.' : `Manage ${section.toLowerCase()} for ${workspaceName}.`)}</p></div>{section !== 'Platform' && <div className="heading-actions"><button className="button secondary" onClick={() => exportCsv(jobs)} disabled={!jobs.length}>Export report</button><button className="button primary" onClick={() => setShowNew(true)} disabled={!tenantId}>+ New order</button></div>}</div>
        {justCreated && <div className="notice" role="status"><span className="notice-icon">✓</span><div><b>Order created. Now give it a driver.</b><span>Click the order below and choose a driver under Assigned driver. To assign several at once, open the Dispatch board.</span></div><button onClick={() => setJustCreated(false)}>Dismiss</button></div>}
        {loadError && <div className="notice" role="alert"><span className="notice-icon">!</span><div><b>Could not load data</b><span>{loadError}</span></div><button onClick={() => { setLoading(true); load(); }}>Retry <span>→</span></button></div>}
        {!loadError && attention > 0 && section !== 'Overview' && section !== 'Drivers' && section !== 'Settings' && section !== 'Platform' && <div className="notice"><span className="notice-icon">!</span><div><b>{attention} {attention === 1 ? 'item needs' : 'items need'} attention</b><span>{stats.exceptions} exception{stats.exceptions === 1 ? '' : 's'}, {stats.lowConfidence} low-confidence location{stats.lowConfidence === 1 ? '' : 's'} and {openRecon.length} open COD reconciliation item{openRecon.length === 1 ? '' : 's'}.</span></div><button onClick={() => { setFilter('exception'); setSection('Dispatch board'); }}>Review exceptions <span>→</span></button></div>}
        {section === 'Overview' && !loadError && <div className="needs-action" aria-label="Needs action">{([
          [stats.unassigned, 'waiting for a driver', () => { setFilter('pending'); setSection('Orders'); }],
          [stats.exceptions, 'exceptions to review', () => { setFilter('exception'); setSection('Orders'); }],
          [stats.lowConfidence, 'addresses to confirm', () => setSection('Orders')],
          [openRecon.length, 'cash items to reconcile', () => setSection('Reconciliation')]
        ] as [number, string, () => void][]).map(([count, text, go], index) => <button key={text} className={`action-tile tone-${['amber', 'red', 'violet', 'blue'][index]}${count ? ' hot' : ''}`} onClick={go}><b>{count}</b><span>{text}</span></button>)}</div>}
        {section === 'Overview' && <div className="metric-grid"><Metric label="Total jobs" value={String(jobs.length)} detail={`${stats.unassigned} unassigned`} warning={stats.unassigned > 0} sub="awaiting dispatch" /><Metric label="Delivered" value={deliveredPct} detail={`${stats.delivered} of ${jobs.length}`} positive sub="of all jobs" /><Metric label="Exceptions" value={String(stats.exceptions)} detail={stats.exceptions ? 'needs review' : 'all clear'} warning={stats.exceptions > 0} positive={stats.exceptions === 0} sub="failed, returned or cancelled" /><Metric label="COD to reconcile" value={money.format(stats.reconVariance)} detail={`${openRecon.length} open item${openRecon.length === 1 ? '' : 's'}`} warning={openRecon.length > 0} sub="variance needing review" /></div>}
        {section === 'Overview' && tenantId && <SetupChecklist api={api} tenantId={tenantId} refreshKey={refreshTick} onGo={goTo} />}
        {section === 'Overview' && tenantId && <InsightsPanel api={api} tenantId={tenantId} refreshKey={refreshTick} />}
        {section === 'Dispatch board' && tenantId && <ExceptionsPanel api={api} tenantId={tenantId} refreshKey={refreshTick} onOpen={(orderId) => { const match = jobs.find((job) => job.orderId === orderId); if (match) setSelected(match); }} />}
        {section === 'Dispatch board' && tenantId && <DispatchBatches api={api} tenantId={tenantId} onChanged={load} refreshKey={refreshTick} />}
        {(section === 'Overview' || section === 'Dispatch board' || section === 'Orders') && <><div className="section-head"><div><h2>{section === 'Overview' ? 'Latest orders' : section === 'Orders' ? 'All orders' : 'Delivery operations'}</h2><p>{section === 'Overview' ? 'The five most recent deliveries' : 'Live view of jobs across your workspace'}</p></div><div className="segmented">{(['all', 'pending', 'en_route', 'exception'] as const).map((value) => <button key={value} className={filter === value ? 'selected' : ''} onClick={() => setFilter(value)}>{({ all: 'All jobs', pending: 'Unassigned', en_route: 'In transit', exception: 'Exceptions' })[value]}</button>)}</div></div>
        <div className={section === 'Orders' ? 'operations-grid single' : 'operations-grid'}><div className="job-table card"><div className="table-toolbar"><div className="table-title"><b>{filtered.length} jobs</b><span>{loading ? 'Loading…' : updatedAt ? `Updated ${new Date(updatedAt).toLocaleTimeString()}` : ''}</span></div><div className="popover-anchor"><button className="filter-button" aria-expanded={filterOpen} onClick={() => setFilterOpen(!filterOpen)}>{filter === 'all' ? 'Filter' : labels[filter]} <span>⌄</span></button>{filterOpen && <div className="popover" role="menu">{(['all', 'pending', 'assigned', 'en_route', 'arrived', 'delivered', 'exception'] as const).map((value) => <button key={value} role="menuitem" className={filter === value ? 'selected' : ''} onClick={() => { setFilter(value); setFilterOpen(false); }}>{value === 'all' ? 'All statuses' : labels[value]}</button>)}</div>}</div></div><div className="table-scroll"><table><thead><tr><th>ORDER</th><th>CUSTOMER</th><th>LOCATION</th><th>STATUS</th><th>DRIVER</th><th>COD AMOUNT</th><th /></tr></thead><tbody>{loading && !jobs.length && [0, 1, 2].map((row) => <tr key={`sk${row}`} aria-hidden="true"><td colSpan={7}><div className="skeleton" /></td></tr>)}{!loading && !filtered.length && <tr><td colSpan={7} className="muted">{loadError ? 'We could not load your jobs just now.' : jobs.length ? 'Nothing matches that search or filter. Try clearing it.' : 'No deliveries yet. Create your first order and it will show up here.'}</td></tr>}{rows.map((job) => <tr key={job.id} tabIndex={0} onClick={() => setSelected(job)} onKeyDown={(event) => { if (event.key === 'Enter') setSelected(job); }}><td><b className="order-id">{job.order}</b><small>{job.time}</small></td><td><b>{job.customer}</b><small>{job.merchant}</small></td><td><b>{job.area}</b><small className={job.confidence === 'Low' ? 'low-confidence' : ''}>{job.landmark}</small></td><td><StatusTrack status={job.status} /></td><td>{job.driver ? <span className="driver"><span className="mini-avatar">{initials(job.driver)}</span>{job.driver}</span> : <span className="unassigned">Unassigned</span>}</td><td><b>{money.format(job.amount)}</b><small>COD</small></td><td><span className="row-arrow">→</span></td></tr>)}</tbody></table></div><div className="table-footer"><span>Showing {rows.length} of {jobs.length} jobs</span>{section === 'Overview' ? <button onClick={() => setSection('Orders')}>View all orders →</button> : <button onClick={() => setSection('Dispatch board')}>Open dispatch board →</button>}</div></div>{section !== 'Orders' && <SidePanels jobs={jobs} api={api} tenantId={tenantId} onOpenMap={() => setSection('Live map')} />}</div></>}
        {section === 'Live map' && tenantId && <LiveTracking api={api} tenantId={tenantId} />}
        {section === 'Platform' && profile?.is_platform_admin && <PlatformConsole api={api} myId={profile.subject} />}
        {section === 'Drivers' && tenantId && <DriversView api={api} tenantId={tenantId} />}
        {section === 'Reconciliation' && tenantId && <><FinanceTools api={api} tenantId={tenantId} onChanged={load} /><ClaimsPanel api={api} tenantId={tenantId} canDecide={['tenant_owner', 'tenant_admin', 'operations_manager', 'finance', 'dev'].includes(tenant?.role ?? '')} /></>}
        {section === 'Reconciliation' && tenantId && <ReconciliationView api={api} tenantId={tenantId} items={recon} onChanged={load} />}
        {section === 'Settings' && tenantId && <SettingsPanels api={api} tenantId={tenantId} tenant={tenant} initialTab={settingsTab} onRenamed={reloadTenant} />}
      </div>
    </section>
    {selected && tenantId && <JobDrawer job={selected} api={api} tenantId={tenantId} onChanged={load} close={() => setSelected(null)} />}
    {showNew && tenantId && <NewOrderModal api={api} tenantId={tenantId} onChanged={() => { load(); setFilter('pending'); setQuery(''); if (!['Overview', 'Dispatch board', 'Orders'].includes(section)) setSection('Orders'); setJustCreated(true); }} close={() => setShowNew(false)} />}
  </main>;
}

const STEPS: Status[] = ['pending', 'assigned', 'en_route', 'arrived', 'delivered'];
/** A delivery's progress drawn like a road: how far the parcel has got, with the status in words beside it. */
function StatusTrack({ status }: { status: Status }) {
  const reached = status === 'exception' ? 1 : STEPS.indexOf(status) + 1;
  return <span className={`track track-${status}`} role="img" aria-label={labels[status]}>
    <span className="track-road" aria-hidden="true">{STEPS.map((step, index) => <i key={step} className={index < reached ? 'on' : ''} />)}</span>
    <span className="track-label">{labels[status]}</span>
  </span>;
}

function Metric({ label, value, detail, positive, warning, sub }: { label: string; value: string; detail: string; positive?: boolean; warning?: boolean; sub: string }) { return <div className="metric card"><div className="metric-label">{label}<span className="info">i</span></div><div className="metric-value">{value}</div><div className={`metric-detail ${positive ? 'positive' : warning ? 'warning' : ''}`}>{detail}</div><span className="metric-sub">{sub}</span></div>; }
function SidePanels({ jobs, api, tenantId, onOpenMap }: { jobs: Job[]; api: ApiClient; tenantId?: string; onOpenMap: () => void }) {
  const activeDrivers = new Set(jobs.filter((job) => job.driver && (job.status === 'en_route' || job.status === 'arrived' || job.status === 'assigned')).map((job) => job.driver)).size;
  const today = new Date();
  const days = Array.from({ length: 7 }, (_, index) => { const day = new Date(today); day.setDate(today.getDate() - (6 - index)); return day; });
  const totals = days.map((day) => jobs.filter((job) => job.status === 'delivered' && dayKey(new Date(job.createdAt.endsWith('Z') ? job.createdAt : `${job.createdAt}Z`)) === dayKey(day)).reduce((sum, job) => sum + job.amount, 0));
  const peak = Math.max(...totals, 1);
  const weekTotal = totals.reduce((sum, value) => sum + value, 0);
  return <div className="side-column">{tenantId ? <MiniLiveMap api={api} tenantId={tenantId} onOpen={onOpenMap} /> : <div className="map-card card"><div className="map-header"><div><b>Live map</b><small>{activeDrivers} driver{activeDrivers === 1 ? '' : 's'} on active jobs</small></div></div></div>}<div className="recon-card card"><div className="recon-heading"><div><b>COD delivered</b><small>Last 7 days</small></div></div><div className="recon-total">{money.format(weekTotal)} <span>delivered</span></div><div className="bars">{totals.map((value, index) => <i key={index} className={index === 6 ? 'today' : ''} style={{ height: `${Math.max(4, (value / peak) * 100)}%` }} />)}</div><div className="days">{days.map((day, index) => <span key={index}>{index === 6 ? 'Today' : day.toLocaleDateString('en', { weekday: 'narrow' })}</span>)}</div></div></div>;
}
