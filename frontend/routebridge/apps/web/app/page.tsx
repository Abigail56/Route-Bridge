'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LiveStreamStatus } from '../components/live-stream-status';
import { ThemeToggle } from '../components/theme-toggle';
import { AccountMenu } from '../components/account-menu';
import { FirstRunScreen, SetupChecklist } from '../components/onboarding';
import { PlatformConsole } from '../components/platform-views';
import { MerchantPortal } from '../components/merchant-portal';
import { LiveTracking, MiniLiveMap } from '../components/tracking-views';
import { ClaimsPanel, DispatchBatches, ExceptionsPanel, FinanceTools, InsightsPanel, MerchantsView, ReportsView, SettingsPanels } from '../components/admin-views';
import { roleName } from '../lib/roles';
import { DriversView, JobDrawer, ReconciliationView } from '../components/workspace-views';
import { createApiClient, friendlyMessage, type ApiClient, type JoinRequest, type ReconciliationItem } from '../lib/api';
import { freshRequests, requestText, toSeen, type SeenRequests } from '../lib/join-requests';
import { JoinRequestsPanel } from '../components/join-requests';
import { DeliveryCodePanel } from '../components/delivery-codes';
import { useGetToken } from '../lib/auth-token';
import { ACTIVE, arrivedAt, filterJobs, matchesFilter, toJob, toAmount, type Job, type JobFilter, type Status } from '../lib/jobs';
import { useEventStream } from '../lib/use-event-stream';
import { useTenant } from '../lib/use-tenant';
import { StatusToasts, type Toast } from '../components/status-toasts';
import { newOrders, statusChanges, toSnapshot, type Snapshot } from '../lib/status-updates';
import { playJoinChime, playOrderChime, unlockOrderChime } from '../lib/order-chime';
import { useAuth } from '../lib/auth';
import { Landing } from '../components/landing';

const labels: Record<Status, string> = { pending: 'Unassigned', assigned: 'Driver assigned', accepted: 'Accepted', en_route: 'On the way', arrived: 'At the door', delivered: 'Delivered', exception: 'Problem' };
const FILTER_LABELS: Record<JobFilter, string> = { all: 'All', active: 'Active', ...labels };
const QUICK_FILTERS: JobFilter[] = ['all', 'pending', 'active', 'delivered', 'exception'];
const MENU_FILTERS: JobFilter[] = ['all', 'pending', 'assigned', 'accepted', 'en_route', 'arrived', 'delivered', 'exception'];
// how often the console re-reads the orders, even while the live stream is connected (it can be connected and still silent)
const POLL_MS = 10_000;
const PAGE_SIZE = 25;
const money = new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 0 });

function initials(name?: string) { return name ? name.split(' ').map((part) => part[0]).join('') : ''; }
function Icon({ type }: { type: 'overview' | 'dispatch' | 'orders' | 'drivers' | 'merchants' | 'finance' | 'reports' | 'settings' | 'platform' | 'map' | 'problems' }) {
  const path = { merchants: 'M4 10h16v10H4zM3 10l2-6h14l2 6M10 20v-5h4v5', reports: 'M7 3h7l5 5v13H7zM14 3v5h5M10 17v-3M13 17v-6M16 17v-2', problems: 'M4 5h16v11H10l-5 4v-4H4z', map: 'M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 7zM9 4v13M15 7v12.5', platform: 'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6zM9 12l2 2 4-4', overview: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z', dispatch: 'M3 6h11v10H3zM14 10h4l3 3v3h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z', orders: 'M4 7 12 3l8 4-8 4-8-4Zm0 0v10l8 4 8-4V7M12 11v10', drivers: 'M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-3 4v1M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM20 20v-1a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75', finance: 'M4 19V5M4 19h17M8 16v-4M12 16V8M16 16v-7M20 16v-3', settings: 'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z' }[type];
  return <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={path} /></svg>;
}

// Each console page has its own address, so links, refresh and the back button all work.
const PATHS: Record<string, string> = { Overview: '/', 'Dispatch board': '/dispatch', 'Live map': '/tracking', Orders: '/orders', Drivers: '/drivers', Merchants: '/merchants', Reconciliation: '/reconciliation', Reports: '/reports', Problems: '/problems', Settings: '/settings', Platform: '/platform' };
function sectionFromPath(path: string) {
  const clean = path.replace(/\/+$/, '') || '/';
  return Object.keys(PATHS).find((label) => PATHS[label] === clean) ?? 'Overview';
}

function greetingFor(date: Date) { const h = date.getHours(); return h >= 5 && h < 12 ? 'Good morning' : h >= 12 && h < 17 ? 'Good afternoon' : 'Good evening'; }
function initialsOf(text: string) { return text.split(' ').filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase() || 'RB'; }
function dayKey(date: Date) { return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`; }

function exportCsv(jobs: Job[]) {
  const escape = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`;
  const rows = [['Order', 'Customer', 'Merchant', 'Location', 'Landmark', 'Status', 'Driver', 'Cash on delivery', 'Arrived'], ...jobs.map((job) => [job.order, job.customer, job.merchant, job.area, job.landmark, job.status, job.driver ?? '', job.amount, job.createdAt])];
  const url = URL.createObjectURL(new Blob([rows.map((row) => row.map(escape).join(',')).join('\r\n')],{ type: 'text/csv' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'routebridge-jobs.csv';
  link.click();
  URL.revokeObjectURL(url);
}

// Signed-out visitors at "/" get the public front page (the middleware lets only that exact path through without a session);
// everyone signed in gets their console.
export default function Home() {
  const auth = useAuth();
  if (!auth.isLoaded) return null;
  if (!auth.isSignedIn) return <Landing />;
  return <Console />;
}

function Console() {
  const getToken = useGetToken();
  const api = useMemo(() => createApiClient(getToken), [getToken]);
  const { tenant, profile, status: tenantStatus, error: tenantError, reload: reloadTenant } = useTenant(api);
  const [settingsTab, setSettingsTab] = useState<'members' | 'merchants' | 'zones' | 'audit' | undefined>(undefined);
  const tenantId = tenant?.tenant_id;
  const isMerchant = tenant?.role === 'merchant_user';
  // a Dispatcher (rider) does not use the console: they go to the rider app, which shows only their own orders
  const isRider = tenant?.role === 'driver';
  const noConsole = isMerchant || isRider;
  const [jobs, setJobs] = useState<Job[]>([]);
  const [recon, setRecon] = useState<ReconciliationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!tenantId || noConsole) return;
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
  }, [api, tenantId, noConsole]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!isRider || !tenantId) return;
    api.myRiderToken(tenantId).then((pass) => window.location.replace(`/driver#token=${encodeURIComponent(pass.access_token)}`)).catch((exc) => setLoadError(friendlyMessage(exc)));
  }, [api, isRider, tenantId]);
  useEffect(() => { if (tenantError) { setLoadError(tenantError); setLoading(false); } }, [tenantError]);

  // Refresh when the backend announces a change; coalesce bursts of events into one reload.
  const [refreshTick, setRefreshTick] = useState(0);
  useEffect(() => {
    if (!refreshTick) return;
    const timer = setTimeout(load, 400);
    return () => clearTimeout(timer);
  }, [refreshTick, load]);
  const streamState = useEventStream(noConsole ? undefined : tenantId, getToken, () => setRefreshTick((tick) => tick + 1));
  // The stream makes changes instant; this makes them certain. A rider's accept, start, arrive or deliver shows within 10 seconds
  // even when the stream is down or connected but silent (outbox worker stopped), and straight away when the tab comes back.
  useEffect(() => {
    if (noConsole || !tenantId) return;
    const look = () => { if (document.visibilityState === 'visible') setRefreshTick((tick) => tick + 1); };
    const timer = setInterval(look, POLL_MS);
    document.addEventListener('visibilitychange', look);
    window.addEventListener('focus', look);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', look); window.removeEventListener('focus', look); };
  }, [noConsole, tenantId]);

  // Say what changed: "The rider accepted order RB-104", "Order RB-104 is on the way", "... was delivered".
  // A brand-new order from a shop also plays a short chime, so the Admin hears it without watching the screen.
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seen = useRef<Snapshot | null>(null);
  useEffect(() => (noConsole ? undefined : unlockOrderChime()), [noConsole]);
  useEffect(() => {
    if (loading) return;
    const rows = jobs.map((job) => ({ id: job.id, external_ref: job.order, status: job.rawStatus, code_verified: job.codeVerified, merchant: job.merchant }));
    const placed = newOrders(seen.current, rows);
    const found = [...placed, ...statusChanges(seen.current, rows)];
    seen.current = toSnapshot(rows);
    if (placed.length) playOrderChime();
    if (found.length) setToasts((current) => [...found.map((change) => ({ id: `${change.id}-${change.to}-${Date.now()}`, text: change.text, tone: change.tone })), ...current].slice(0, 4));
  }, [jobs, loading]);
  const dismissToast = useCallback((id: string) => setToasts((current) => current.filter((toast) => toast.id !== id)), []);

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

  // problems the shops sent that still wait for the company's reply (badge, alert and tile); checked every 20 seconds
  const [problemsWaiting, setProblemsWaiting] = useState(0);
  useEffect(() => {
    if (!tenantId || noConsole || isRider) return;
    let stop = false;
    const check = () => { api.getClaims(tenantId).then((rows) => { if (!stop) setProblemsWaiting(rows.filter((row) => row.awaiting_company).length); }).catch(() => undefined); };
    check();
    const timer = window.setInterval(() => { if (!document.hidden) check(); }, 20000);
    return () => { stop = true; window.clearInterval(timer); };
  }, [api, tenantId, noConsole, isRider]);

  // people who signed up and pressed "Send to the Admin" (owner and admin only): checked every 15 seconds; a new one plays its own
  // three-note sound, shows a toast and a bell alert, and waits on the Overview with one-press Add buttons
  const seesJoinRequests = ['tenant_owner', 'tenant_admin'].includes(tenant?.role ?? '');
  const [joinRequests, setJoinRequests] = useState<JoinRequest[]>([]);
  const joinSeen = useRef<SeenRequests | null>(null);
  const loadJoinRequests = useCallback(() => {
    if (!tenantId || !seesJoinRequests) return;
    api.getJoinRequests(tenantId).then((rows) => {
      const fresh = freshRequests(joinSeen.current, rows);
      joinSeen.current = toSeen(rows);
      setJoinRequests(rows);
      if (!fresh.length) return;
      playJoinChime();
      setToasts((current) => [...fresh.map((row) => ({ id: `join-${row.id}-${row.sent_at}`, text: requestText(row), tone: 'info' as const })), ...current].slice(0, 4));
    }).catch(() => undefined);
  }, [api, tenantId, seesJoinRequests]);
  useEffect(() => {
    if (noConsole || isRider || !tenantId || !seesJoinRequests) return;
    joinSeen.current = null;
    loadJoinRequests();
    const timer = window.setInterval(() => { if (!document.hidden) loadJoinRequests(); }, 15000);
    return () => window.clearInterval(timer);
  }, [loadJoinRequests, noConsole, isRider, tenantId, seesJoinRequests]);

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
  const [filter, setFilter] = useState<JobFilter>('all');
  // keep only the id, so an open order shows its new status as soon as the list reloads
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = useMemo(() => jobs.find((job) => job.id === selectedId) ?? null, [jobs, selectedId]);
  const setSelected = (job: Job | null) => setSelectedId(job?.id ?? null);
  const [now, setNow] = useState(() => new Date());
  // Sidebar: on a wide screen it is open unless the person closed it (remembered); on a narrow one it is a drawer that starts closed.
  const [wide, setWide] = useState(true);
  const [sidebarClosed, setSidebarClosed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  useEffect(() => {
    try { setSidebarClosed(window.localStorage.getItem('rb_sidebar') === 'closed'); } catch { /* storage can be blocked */ }
    const query = window.matchMedia('(min-width: 1024px)');
    const sync = () => { setWide(query.matches); if (query.matches) setDrawerOpen(false); };
    sync();
    query.addEventListener('change', sync);
    return () => query.removeEventListener('change', sync);
  }, []);
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setDrawerOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawerOpen]);
  const toggleSidebar = () => {
    if (!wide) { setDrawerOpen((open) => !open); return; }
    const next = !sidebarClosed;
    setSidebarClosed(next);
    try { window.localStorage.setItem('rb_sidebar', next ? 'closed' : 'open'); } catch { /* the choice just is not remembered */ }
    if (next) document.documentElement.dataset.sidebar = 'closed'; else delete document.documentElement.dataset.sidebar;
  };
  const sidebarOpen = wide ? !sidebarClosed : drawerOpen;
  useEffect(() => { const timer = setInterval(() => setNow(new Date()), 60_000); return () => clearInterval(timer); }, []);
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [bellOpen, setBellOpen] = useState(false);
  const [codeCount, setCodeCount] = useState(0);
  const [platformOnly, setPlatformOnly] = useState(false);
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);
  // The Admin (platform admin) signing in to a site with no company yet gets "RouteBridge" made for them at once, and lands
  // straight on the Admin console to add shops and drivers. Only when no company exists at all; otherwise nothing is guessed.
  const [settingUp, setSettingUp] = useState(false);
  const autoSetup = useRef(false);
  useEffect(() => {
    if (tenantStatus !== 'needs-workspace' || !profile?.is_platform_admin || autoSetup.current) return;
    autoSetup.current = true;
    setSettingUp(true);
    api.platform.companies()
      .then((rows) => (rows.length ? undefined : api.createTenant('RouteBridge').then(() => reloadTenant())))
      .catch(() => undefined)
      .finally(() => setSettingUp(false));
  }, [tenantStatus, profile, api, reloadTenant]);
  const [filterOpen, setFilterOpen] = useState(false);
  const filtered = useMemo(() => filterJobs(jobs, filter, query), [filter, jobs, query]);
  const countFor = (value: JobFilter) => jobs.filter((job) => matchesFilter(job, value)).length;
  // the full lists show 25 orders a page; the page goes back to the first whenever what is shown changes
  const [page, setPage] = useState(0);
  useEffect(() => { setPage(0); }, [filter, query, section]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const rows = section === 'Overview' ? filtered.slice(0, 5) : filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const baseNav = [['Overview', 'overview'], ['Dispatch board', 'dispatch'], ['Live map', 'map'], ['Orders', 'orders'], ['Drivers', 'drivers'], ['Merchants', 'merchants'], ['Problems', 'problems'], ['Reconciliation', 'finance'], ['Reports', 'reports'], ['Settings', 'settings']] as const;
  // the Platform console is not part of the Admin's menu; it stays reachable at /platform for platform administrators
  const nav = baseNav;
  const workspaceName = tenant?.name || 'Your workspace';
  const firstName = (profile?.name || '').trim().split(/\s+/)[0] || '';
  const roleLabel = roleName(tenant?.role);
  type Alert = { title: string; hint: string; target: string; filter?: JobFilter; tone: 'amber' | 'red' | 'violet' | 'blue' };
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const alerts: Alert[] = [
    ...(joinRequests.length ? [{ title: `${plural(joinRequests.length, 'person wants', 'people want')} to join`, hint: 'A new shop or driver sent you their ID. Add them on the Overview.', target: 'Overview', tone: 'blue' as const }] : []),
    ...(codeCount ? [{ title: `${plural(codeCount, 'rider is', 'riders are')} waiting for a delivery code`, hint: 'Send the code to the customer, then press Mark as sent.', target: 'Dispatch board', tone: 'red' as const }] : []),
    ...(stats.unassigned ? [{ title: `${plural(stats.unassigned, 'job is', 'jobs are')} waiting for a driver`, hint: 'Open the list and assign a rider.', target: 'Orders', filter: 'pending' as Status, tone: 'amber' as const }] : []),
    ...(stats.exceptions ? [{ title: `${plural(stats.exceptions, 'delivery needs', 'deliveries need')} your review`, hint: 'These failed, were returned or were cancelled.', target: 'Orders', filter: 'exception' as Status, tone: 'red' as const }] : []),
    ...(stats.lowConfidence ? [{ title: `${plural(stats.lowConfidence, 'address', 'addresses')} to confirm`, hint: 'The map position is uncertain. A rider may struggle to find it.', target: 'Orders', tone: 'violet' as const }] : []),
    ...(problemsWaiting ? [{ title: `${plural(problemsWaiting, 'problem', 'problems')} from your shops ${problemsWaiting === 1 ? 'waits' : 'wait'} for your reply`, hint: 'A shop reported a damaged, lost or disputed delivery.', target: 'Problems', tone: 'red' as const }] : []),
    ...(openRecon.length ? [{ title: `${plural(openRecon.length, 'cash item', 'cash items')} to reconcile`, hint: 'Cash collected does not yet match what was expected.', target: 'Reconciliation', tone: 'blue' as const }] : [])
  ];
  const attention = stats.exceptions + stats.lowConfidence + openRecon.length;
  const deliveredPct = jobs.length ? `${((stats.delivered / jobs.length) * 100).toFixed(1)}%` : '—';

  const goTo = (target: string, tab?: 'members' | 'merchants' | 'zones') => { setSection(target); if (tab) setSettingsTab(tab); };
  const accountMenu = <AccountMenu />;
  if (tenantStatus === 'loading') return <main style={{ maxWidth: 420, margin: '20vh auto', textAlign: 'center' }}>Loading your workspace…</main>;
  if (isRider) return <main className="portal-loading" style={{ padding: 24 }}><p>{loadError || 'Opening your orders…'}</p></main>;
  if (isMerchant && tenant) return <MerchantPortal api={api} tenant={tenant} firstName={firstName} accountMenu={accountMenu} />;
  // a platform administrator without a workspace lands on the Platform console; "Create workspace" there opens the first-run form,
  // which is otherwise unreachable for them (after a fresh start there is no company yet and only they can create one)
  if (settingUp) return <main style={{ maxWidth: 420, margin: '20vh auto', textAlign: 'center' }}>Setting up your RouteBridge workspace…</main>;
  if (tenantStatus === 'needs-workspace' && profile && !creatingWorkspace && (platformOnly || profile.is_platform_admin)) return <main className="page-wrap"><div className="page-heading"><div><div className="breadcrumb">ROUTEBRIDGE</div><h1>Platform console</h1><p>Manage every company on RouteBridge.</p></div><div className="heading-actions">{!profile.is_platform_admin && <button className="button secondary" onClick={() => setPlatformOnly(false)}>Back</button>}{profile.is_platform_admin && <button className="button primary" onClick={() => setCreatingWorkspace(true)}>Create workspace</button>}{accountMenu}</div></div><PlatformConsole api={api} myId={profile.subject} /></main>;
  if (tenantStatus === 'needs-workspace' && profile) return <FirstRunScreen api={api} profile={profile} onCreated={reloadTenant} accountMenu={accountMenu} onOpenPlatform={profile.is_platform_admin ? () => { setCreatingWorkspace(false); setPlatformOnly(true); } : undefined} />;

  return <main className={drawerOpen ? 'app-shell nav-open' : 'app-shell'}>
    <aside className="sidebar" id="app-sidebar" aria-label="Main menu">
      <button type="button" className="nav-toggle in-sidebar" onClick={toggleSidebar} aria-label={sidebarOpen ? 'Close the menu' : 'Open the menu'} aria-expanded={sidebarOpen} aria-controls="app-sidebar"><span /><span /><span /></button>
      <div className="brand"><div className="brand-mark" role="img" aria-label="RouteBridge logo" /><div><strong>RouteBridge</strong><span>Operations console</span></div></div>
      <div className="workspace"><span className="eyebrow">WORKSPACE</span><div className="workspace-row"><div className="workspace-avatar">{initialsOf(workspaceName)}</div><div><b>{workspaceName}</b><small>{roleLabel}</small></div></div></div>
      <nav className="nav">{nav.map(([label, icon]) => <a key={label} href={PATHS[label]} aria-current={section === label ? 'page' : undefined} className={section === label ? 'nav-item active' : 'nav-item'} onClick={(event) => { event.preventDefault(); setSection(label); setDrawerOpen(false); }}><Icon type={icon} /><span>{label}</span>{label === 'Reconciliation' && openRecon.length > 0 && <em>{openRecon.length}</em>}{label === 'Problems' && problemsWaiting > 0 && <em>{problemsWaiting}</em>}</a>)}</nav>
      <div className="sidebar-bottom"><div className="pilot-card"><div className="pilot-dot" /><div><b>{streamState === 'live' ? 'Live updates on' : 'Checking every 10 s'}</b><small>{updatedAt ? `Last update ${new Date(updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : 'Loading…'}</small></div></div></div>
    </aside>
    {drawerOpen && <div className="sidebar-backdrop" onClick={() => setDrawerOpen(false)} aria-hidden="true" />}
    <section className="content">
      <header className="topbar"><button type="button" className="nav-toggle open-menu" onClick={toggleSidebar} aria-label={sidebarOpen ? 'Close the menu' : 'Open the menu'} aria-expanded={sidebarOpen} aria-controls="app-sidebar"><span /><span /><span /></button><div className="mobile-brand"><div className="brand-mark" role="img" aria-label="RouteBridge logo" /><strong>RouteBridge</strong></div><div className="top-actions"><ThemeToggle /><LiveStreamStatus state={streamState} />{searchOpen && <input className="topbar-search" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Escape') { setQuery(''); setSearchOpen(false); } }} placeholder="Search orders, customers, areas…" aria-label="Search jobs" />}<button className="icon-btn" aria-label="Search" onClick={() => { if (searchOpen && query) setQuery(''); setSearchOpen(!searchOpen); if (!searchOpen && !['Overview', 'Dispatch board', 'Orders'].includes(section)) setSection('Orders'); }}><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4" /></svg></button><div className="popover-anchor"><button className="icon-btn notification" aria-label="Notifications" aria-expanded={bellOpen} onClick={() => setBellOpen(!bellOpen)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" /></svg><i /></button>{bellOpen && <div className="popover popover-notifications" role="menu"><div className="popover-title"><b>Notifications</b><span>{alerts.length ? `${alerts.length} need${alerts.length === 1 ? 's' : ''} your attention` : 'All clear'}</span></div>{alerts.length ? alerts.map((alert) => <button key={alert.title} role="menuitem" className={`alert-item tone-${alert.tone}`} onClick={() => { setBellOpen(false); if (alert.filter) setFilter(alert.filter); goTo(alert.target); }}><span className="alert-dot" aria-hidden="true" /><span className="alert-text"><b>{alert.title}</b><small>{alert.hint}</small></span><span className="alert-go" aria-hidden="true">›</span></button>) : <div className="alert-empty"><b>You are all caught up</b><p>Nothing needs your attention right now.</p></div>}</div>}</div>{accountMenu ?? <div className="top-avatar">{initialsOf(workspaceName)}</div>}</div></header>
      <div className="page-wrap">
        {section === 'Overview' && <section className="hero" aria-label="Today">
          <div className="hero-copy">
            <span className="hero-date">{now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</span>
            <h1>{greetingFor(now)}{firstName ? `, ${firstName}` : ''}</h1>
            <p className="hero-sub">{jobs.length ? `${jobs.filter((job) => ACTIVE.includes(job.status)).length} on the road, ${stats.unassigned} waiting for a driver, ${stats.delivered} delivered.` : 'No orders yet. They appear here as soon as a shop places one.'}</p>
            <div className="hero-actions"><button className="hero-btn solid" onClick={() => setSection('Dispatch board')}>Open dispatch board</button><button className="hero-btn ghost" onClick={() => exportCsv(jobs)} disabled={!jobs.length}>Export CSV</button></div>
          </div>
        </section>}
        <div className={section === 'Overview' ? 'page-heading is-overview' : 'page-heading'}><div><div className="breadcrumb">{workspaceName.toUpperCase()} <span>/</span> TODAY</div><h1>{section === 'Overview' ? `${greetingFor(now)}${firstName ? `, ${firstName}` : ''}` : section}</h1><p>{section === 'Overview' ? 'What needs your attention today.' : (section === 'Platform' ? 'Run RouteBridge itself: companies, people, administrators, health and audit.' : section === 'Live map' ? 'See where every rider is and how close they are to the door.' : section === 'Drivers' ? 'Your riders. Give each one a link or QR code to sign in on their phone.' : section === 'Merchants' ? 'The shops you deliver for, their details and their subscriptions.' : section === 'Reports' ? 'Delivery performance, cash on delivery and failure reasons.' : `Manage ${section.toLowerCase()} for ${workspaceName}.`)}</p></div>{section !== 'Platform' && <div className="heading-actions"><button className="button secondary" onClick={() => exportCsv(jobs)} disabled={!jobs.length}>Export CSV</button></div>}</div>
        {tenantId && <DeliveryCodePanel api={api} tenantId={tenantId} refreshKey={refreshTick} onCount={setCodeCount} />}
        {loadError && <div className="notice" role="alert"><span className="notice-icon">!</span><div><b>Could not load data</b><span>{loadError}</span></div><button onClick={() => { setLoading(true); load(); }}>Retry <span>→</span></button></div>}
        {!loadError && attention > 0 && section !== 'Overview' && section !== 'Drivers' && section !== 'Merchants' && section !== 'Reports' && section !== 'Settings' && section !== 'Platform' && <div className="notice"><span className="notice-icon">!</span><div><b>{attention} {attention === 1 ? 'item needs' : 'items need'} attention</b><span>{stats.exceptions} exception{stats.exceptions === 1 ? '' : 's'}, {stats.lowConfidence} low-confidence location{stats.lowConfidence === 1 ? '' : 's'} and {openRecon.length} open COD reconciliation item{openRecon.length === 1 ? '' : 's'}.</span></div><button onClick={() => { setFilter('exception'); setSection('Dispatch board'); }}>Review exceptions <span>→</span></button></div>}
        {section === 'Overview' && !loadError && <div className="needs-action" aria-label="Needs action">{([
          [stats.unassigned, 'waiting for a driver', () => { setFilter('pending'); setSection('Orders'); }],
          [stats.lowConfidence, 'addresses to confirm', () => setSection('Orders')],
          [problemsWaiting, 'problems waiting for your reply', () => setSection('Problems')],
          [openRecon.length, 'cash items to reconcile', () => setSection('Reconciliation')]
        ] as [number, string, () => void][]).map(([count, text, go], index) => <button key={text} className={`action-tile tone-${['amber', 'violet', 'red', 'blue'][index]}${count ? ' hot' : ''}`} onClick={go}><b>{count}</b><span>{text}</span></button>)}</div>}
        {section === 'Overview' && <div className="metric-grid"><Metric label="Total jobs" value={String(jobs.length)} detail={`${stats.unassigned} unassigned`} warning={stats.unassigned > 0} sub="awaiting dispatch" /><Metric label="Delivered" value={deliveredPct} detail={`${stats.delivered} of ${jobs.length}`} positive sub="of all jobs" /><Metric label="COD to reconcile" value={money.format(stats.reconVariance)} detail={`${openRecon.length} open item${openRecon.length === 1 ? '' : 's'}`} warning={openRecon.length > 0} sub="variance needing review" /></div>}
        {section === 'Overview' && tenantId && <JoinRequestsPanel api={api} tenantId={tenantId} rows={joinRequests} canAdd={tenant?.role === 'tenant_owner'} onChanged={loadJoinRequests} />}
        {section === 'Overview' && tenantId && <SetupChecklist api={api} tenantId={tenantId} refreshKey={refreshTick} onGo={goTo} />}
        {section === 'Overview' && tenantId && <InsightsPanel api={api} tenantId={tenantId} refreshKey={refreshTick} />}
        {section === 'Dispatch board' && tenantId && <ExceptionsPanel api={api} tenantId={tenantId} refreshKey={refreshTick} onOpen={(orderId) => { const match = jobs.find((job) => job.orderId === orderId); if (match) setSelected(match); }} />}
        {section === 'Dispatch board' && tenantId && <DispatchBatches api={api} tenantId={tenantId} onChanged={load} refreshKey={refreshTick} />}
        {(section === 'Overview' || section === 'Dispatch board' || section === 'Orders') && <><div className="section-head"><div><h2>{section === 'Overview' ? 'Latest orders' : section === 'Orders' ? 'All orders' : 'Delivery operations'}</h2><p>{section === 'Overview' ? 'The five most recent deliveries' : 'Live view of jobs across your workspace'}</p></div><div className="segmented" role="group" aria-label="Show orders">{QUICK_FILTERS.map((value) => <button key={value} aria-pressed={filter === value} className={filter === value ? 'selected' : ''} onClick={() => setFilter(value)}>{FILTER_LABELS[value]} <span className="seg-count">{countFor(value)}</span></button>)}</div></div>
        <div className={section === 'Orders' ? 'operations-grid single' : 'operations-grid'}><div className="job-table card"><div className="table-toolbar"><div className="table-title"><b>{filtered.length} {filtered.length === 1 ? 'order' : 'orders'}</b><span>{loading ? 'Loading…' : updatedAt ? `Updated ${new Date(updatedAt).toLocaleTimeString()}` : ''}</span></div><div className="popover-anchor"><button className="filter-button" aria-expanded={filterOpen} onClick={() => setFilterOpen(!filterOpen)}>{filter === 'all' ? 'Status: all' : `Status: ${FILTER_LABELS[filter]}`} <span>⌄</span></button>{filterOpen && <><div className="popover-dismiss" onClick={() => setFilterOpen(false)} aria-hidden="true" /><div className="popover" role="menu">{MENU_FILTERS.map((value) => <button key={value} role="menuitemradio" aria-checked={filter === value} className={filter === value ? 'selected' : ''} onClick={() => { setFilter(value); setFilterOpen(false); }}><span>{value === 'all' ? 'All statuses' : FILTER_LABELS[value]}</span><span className="seg-count">{countFor(value)}</span></button>)}</div></>}</div>{(filter !== 'all' || query) && <button className="filter-clear" onClick={() => { setFilter('all'); setQuery(''); setSearchOpen(false); }}>Clear</button>}</div><div className="table-scroll"><table><thead><tr><th>ORDER</th><th>CUSTOMER</th><th>LOCATION</th><th>STATUS</th><th>DRIVER</th><th>CASH ON DELIVERY</th><th /></tr></thead><tbody>{loading && !jobs.length && [0, 1, 2].map((row) => <tr key={`sk${row}`} aria-hidden="true"><td colSpan={7}><div className="skeleton" /></td></tr>)}{!loading && !filtered.length && <tr><td colSpan={7} className="muted">{loadError ? 'We could not load your jobs just now.' : jobs.length ? `No ${filter === 'all' ? '' : `"${FILTER_LABELS[filter]}" `}orders${query ? ` matching "${query}"` : ''}.` : 'No orders yet. Orders your shops place appear here.'}</td></tr>}{rows.map((job) => <tr key={job.id} tabIndex={0} onClick={() => setSelected(job)} onKeyDown={(event) => { if (event.key === 'Enter') setSelected(job); }}><td><b className="order-id">{job.order}</b><small>Arrived {arrivedAt(job.createdAt)}</small><small>{job.time}</small></td><td><b>{job.customer}</b><small>{job.merchant}</small></td><td><b>{job.area}</b><small className={job.confidence === 'Low' ? 'low-confidence' : ''}>{job.landmark}</small></td><td><StatusTrack status={job.status} /></td><td>{job.driver ? <span className="driver"><span className="mini-avatar">{initials(job.driver)}</span>{job.driver}</span> : <span className="unassigned">Unassigned</span>}</td><td><b>{money.format(job.amount)}</b><small>Cash on delivery</small></td><td><span className="row-arrow">→</span></td></tr>)}</tbody></table></div><div className="table-footer"><span>{section === 'Overview' || !filtered.length ? `Showing ${rows.length} of ${filtered.length}` : `Showing ${currentPage * PAGE_SIZE + 1}–${currentPage * PAGE_SIZE + rows.length} of ${filtered.length}`}{filtered.length !== jobs.length ? ` (${jobs.length} in total)` : ''}</span>{section !== 'Overview' && pageCount > 1 && <div className="table-pager" role="navigation" aria-label="Pages"><button type="button" onClick={() => setPage(currentPage - 1)} disabled={currentPage === 0}>Previous</button><span>Page {currentPage + 1} of {pageCount}</span><button type="button" onClick={() => setPage(currentPage + 1)} disabled={currentPage >= pageCount - 1}>Next</button></div>}{section === 'Overview' ? <button onClick={() => setSection('Orders')}>View all orders →</button> : <button onClick={() => setSection('Dispatch board')}>Open dispatch board →</button>}</div></div>{section !== 'Orders' && <SidePanels jobs={jobs} api={api} tenantId={tenantId} onOpenMap={() => setSection('Live map')} />}</div></>}
        {section === 'Live map' && tenantId && <LiveTracking api={api} tenantId={tenantId} />}
        {section === 'Platform' && profile?.is_platform_admin && <PlatformConsole api={api} myId={profile.subject} />}
        {section === 'Drivers' && tenantId && <DriversView api={api} tenantId={tenantId} />}
        {section === 'Problems' && tenantId && <><div className="page-heading"><div><div className="breadcrumb">{workspaceName.toUpperCase()}</div><h1>Problems</h1><p>Damaged or lost goods, refunds and disputes your shops report. Reply here and the shop reads your answer on its own Problems page.</p></div></div><ClaimsPanel api={api} tenantId={tenantId} canDecide={['tenant_owner', 'tenant_admin', 'operations_manager', 'finance', 'dev'].includes(tenant?.role ?? '')} /></>}
        {section === 'Reconciliation' && tenantId && <FinanceTools api={api} tenantId={tenantId} onChanged={load} />}
        {section === 'Reconciliation' && tenantId && <ReconciliationView api={api} tenantId={tenantId} items={recon} onChanged={load} />}
        {section === 'Merchants' && tenantId && <MerchantsView api={api} tenantId={tenantId} tenant={tenant} />}
        {section === 'Reports' && tenantId && <ReportsView api={api} tenantId={tenantId} refreshKey={refreshTick} />}
        {section === 'Settings' && tenantId && <SettingsPanels api={api} tenantId={tenantId} tenant={tenant} initialTab={settingsTab} onRenamed={reloadTenant} />}
      </div>
    </section>
    <StatusToasts toasts={toasts} dismiss={dismissToast} />
    {selected && tenantId && <JobDrawer job={selected} api={api} tenantId={tenantId} onChanged={load} close={() => setSelected(null)} />}
  </main>;
}

const STEPS: Status[] = ['pending', 'assigned', 'accepted', 'en_route', 'arrived', 'delivered'];
/** A delivery's progress drawn like a road: how far the parcel has got, with the status in words beside it. */
function StatusTrack({ status }: { status: Status }) {
  const reached = status === 'exception' ? 1 : STEPS.indexOf(status) + 1;
  return <span className={`track track-${status}`} role="img" aria-label={labels[status]}>
    <span className="track-road" aria-hidden="true">{STEPS.map((step, index) => <i key={step} className={index < reached ? 'on' : ''} />)}</span>
    <span className="track-label">{labels[status]}</span>
  </span>;
}

function Metric({ label, value, detail, positive, warning, sub }: { label: string; value: string; detail: string; positive?: boolean; warning?: boolean; sub: string }) { return <div className="metric card"><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className={`metric-detail ${positive ? 'positive' : warning ? 'warning' : ''}`}>{detail}</div><span className="metric-sub">{sub}</span></div>; }
function SidePanels({ jobs, api, tenantId, onOpenMap }: { jobs: Job[]; api: ApiClient; tenantId?: string; onOpenMap: () => void }) {
  const activeDrivers = new Set(jobs.filter((job) => job.driver && ACTIVE.includes(job.status)).map((job) => job.driver)).size;
  const today = new Date();
  const days = Array.from({ length: 7 }, (_, index) => { const day = new Date(today); day.setDate(today.getDate() - (6 - index)); return day; });
  const totals = days.map((day) => jobs.filter((job) => job.status === 'delivered' && dayKey(new Date(job.createdAt.endsWith('Z') ? job.createdAt : `${job.createdAt}Z`)) === dayKey(day)).reduce((sum, job) => sum + job.amount, 0));
  const peak = Math.max(...totals, 1);
  const weekTotal = totals.reduce((sum, value) => sum + value, 0);
  return <div className="side-column">{tenantId ? <MiniLiveMap api={api} tenantId={tenantId} onOpen={onOpenMap} /> : <div className="map-card card"><div className="map-header"><div><b>Live map</b><small>{activeDrivers} driver{activeDrivers === 1 ? '' : 's'} on active jobs</small></div></div></div>}<div className="recon-card card"><div className="recon-heading"><div><b>COD delivered</b><small>Last 7 days</small></div></div><div className="recon-total">{money.format(weekTotal)} <span>delivered</span></div><div className="bars">{totals.map((value, index) => <i key={index} className={index === 6 ? 'today' : ''} style={{ height: `${Math.max(4, (value / peak) * 100)}%` }} />)}</div><div className="days">{days.map((day, index) => <span key={index}>{index === 6 ? 'Today' : day.toLocaleDateString('en', { weekday: 'narrow' })}</span>)}</div></div></div>;
}
