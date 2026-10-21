// The public front page: what signed-out visitors see at "/". Signed-in people never see it (app/page.tsx shows their console).
// Plan prices are left out on purpose until they are final (config/plans.py still holds placeholders).

const icons = {
  inbox: 'M4 13h4l2 3h4l2-3h4M4 13l2-8h12l2 8v6H4z',
  pin: 'M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21zM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
  eye: 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM4 4l16 16',
  shield: 'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6zM9 12l2 2 4-4',
  cash: 'M3 7h18v10H3zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 10v4M18 10v4',
  signal: 'M4 20v-3M9 20v-7M14 20V9M19 20V4',
  phone: 'M7 3h10v18H7zM11 18h2',
  map: 'M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 7zM9 4v13M15 7v12.5',
  doc: 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6',
  key: 'M14 10a4 4 0 1 0-3.5 4L8 16.5V19h2.5v-2h2v-2l1.4-1.4A4 4 0 0 0 14 10z',
  store: 'M4 10h16v10H4zM3 10l2-6h14l2 6M10 20v-5h4v5',
  truck: 'M3 6h11v10H3zM14 10h4l3 3v3h-7zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  team: 'M16 20v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-3 4v1M9.5 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM20 20v-1a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
};
type IconName = keyof typeof icons;

function LandingIcon({ name }: { name: IconName }) {
  return <svg className="lp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={icons[name]} /></svg>;
}

const problems: { icon: IconName; title: string; text: string }[] = [
  { icon: 'inbox', title: 'Scattered orders', text: 'WhatsApp, Instagram, calls and spreadsheets. No single record.' },
  { icon: 'pin', title: 'Vague addresses', text: '“Opposite the blue church, after the second junction.”' },
  { icon: 'eye', title: 'Blind dispatch', text: 'Nobody knows which rider holds which parcel, or where they are.' },
  { icon: 'shield', title: 'Weak proof', text: 'A rider can say “delivered” when it wasn’t. Disputes follow.' },
  { icon: 'cash', title: 'Leaking cash', text: 'Cash on delivery is reconciled by hand, shop by shop.' },
  { icon: 'signal', title: 'Patchy data', text: 'Riders lose signal mid-route, so online-only apps fail.' },
];

const steps = [
  { title: 'The shop places the order', text: 'From its own portal, with the customer’s landmark, phone and zone.' },
  { title: 'A driver is assigned', text: 'On the Dispatch board, or automatically to a free driver in that zone.' },
  { title: 'The customer watches it come', text: 'A tracking link shows the rider on a map while the parcel is on the way.' },
  { title: 'A code confirms the handover', text: 'The delivery completes only when the customer’s code checks out. Then the cash is settled.' },
];

const features: { icon: IconName; title: string; text: string }[] = [
  { icon: 'key', title: 'No code, no “delivered”', text: 'The customer gets a one-time code the rider never sees. A photo alone is not accepted as proof.' },
  { icon: 'phone', title: 'A driver app that works offline', text: 'Installs from a link. Every step is saved on the phone, encrypted, and sent in order when signal returns.' },
  { icon: 'map', title: 'Live tracking for customers', text: 'No app or sign-in needed. The rider shows on the map only while the parcel is on its way.' },
  { icon: 'doc', title: 'Statements and claims', text: 'Each shop sees cash collected, delivery fees and approved claims, with a reason for every rejected claim.' },
];

const audiences: { icon: IconName; title: string; text: string; join: string }[] = [
  { icon: 'truck', title: 'Delivery companies', text: 'Add your shops and drivers, assign orders, handle problems, reconcile cash and read reports from one console.', join: 'Create an account, then ask RouteBridge to open your company’s workspace.' },
  { icon: 'store', title: 'Shops', text: 'Register once, place delivery orders, follow every parcel live, and see what you are owed.', join: 'Sign up, then send your delivery company the Shop sign-up ID shown on screen.' },
  { icon: 'team', title: 'Drivers', text: 'See only your own jobs, get an alert when one is assigned, and keep working without signal.', join: 'Sign up, register your details, then send the owner your User ID.' },
];

export function Landing() {
  return (
    <div className="lp">
      <header className="lp-hero">
        <nav className="lp-nav" aria-label="Main">
          <a className="lp-brand" href="/"><span className="brand-mark" aria-hidden="true" /><strong>RouteBridge</strong></a>
          <div className="lp-nav-links">
            <a href="#how">How it works</a>
            <a href="#who">Who it’s for</a>
            <a href="#plans">Plans</a>
          </div>
          <div className="lp-nav-actions">
            <a className="lp-btn lp-btn-ghost" href="/sign-in">Sign in</a>
            <a className="lp-btn lp-btn-solid" href="/sign-up">Get started</a>
          </div>
        </nav>
        <div className="lp-hero-copy">
          <p className="lp-eyebrow">Last-mile delivery for Nigeria</p>
          <h1>Every order in one place. Every delivery proven.</h1>
          <p className="lp-lead">RouteBridge runs a delivery company’s shops, drivers, dispatch and cash on delivery in one place. It is built for landmark addresses and patchy mobile data.</p>
          <div className="lp-hero-actions">
            <a className="lp-btn lp-btn-solid lp-btn-lg" href="/sign-up">Get started</a>
            <a className="lp-btn lp-btn-ghost lp-btn-lg" href="/sign-in">Sign in</a>
          </div>
          <p className="lp-note">Shops start with a free 14-day trial. Customers: open the tracking link in your text message.</p>
        </div>
      </header>

      <main>
        <section className="lp-section" aria-labelledby="lp-problem">
          <p className="lp-kicker">The problem</p>
          <h2 id="lp-problem">Same-city delivery in Nigeria runs on calls and trust</h2>
          <div className="lp-grid lp-grid-3">
            {problems.map((item) => (
              <article className="lp-card" key={item.title}><LandingIcon name={item.icon} /><h3>{item.title}</h3><p>{item.text}</p></article>
            ))}
          </div>
        </section>

        <section className="lp-section lp-band" id="how" aria-labelledby="lp-how">
          <p className="lp-kicker">How it works</p>
          <h2 id="lp-how">From the shop’s order to cash in the bank</h2>
          <ol className="lp-steps">
            {steps.map((step, index) => (
              <li key={step.title}><span className="lp-step-number">{index + 1}</span><h3>{step.title}</h3><p>{step.text}</p></li>
            ))}
          </ol>
        </section>

        <section className="lp-section" aria-labelledby="lp-features">
          <p className="lp-kicker">What makes it different</p>
          <h2 id="lp-features">Proof you can trust, even without signal</h2>
          <div className="lp-grid lp-grid-2">
            {features.map((item) => (
              <article className="lp-card lp-card-row" key={item.title}><LandingIcon name={item.icon} /><div><h3>{item.title}</h3><p>{item.text}</p></div></article>
            ))}
          </div>
        </section>

        <section className="lp-section lp-band" id="who" aria-labelledby="lp-who">
          <p className="lp-kicker">Who it’s for</p>
          <h2 id="lp-who">One platform, a screen for everyone</h2>
          <div className="lp-grid lp-grid-3">
            {audiences.map((item) => (
              <article className="lp-card lp-card-top" key={item.title}><LandingIcon name={item.icon} /><h3>{item.title}</h3><p>{item.text}</p><p className="lp-join">{item.join}</p></article>
            ))}
          </div>
        </section>

        <section className="lp-section" id="plans" aria-labelledby="lp-plans">
          <p className="lp-kicker">Plans</p>
          <h2 id="lp-plans">Try it free for 14 days, then a monthly plan</h2>
          <div className="lp-plans">
            <p>Each shop picks Basic, Standard or Pro and pays online through Paystack from its own portal. The trial starts with the shop’s first order.</p>
            <p><b>Deliveries never stop because of billing.</b> If a plan runs out, the shop cannot place new orders until it pays. Parcels already on the road are never touched.</p>
          </div>
        </section>

        <section className="lp-cta" aria-labelledby="lp-cta">
          <h2 id="lp-cta">Ready to run every delivery properly?</h2>
          <p>Create your account. It takes a minute.</p>
          <div className="lp-hero-actions">
            <a className="lp-btn lp-btn-solid lp-btn-lg" href="/sign-up">Get started</a>
            <a className="lp-btn lp-btn-ghost lp-btn-lg" href="/sign-in">Sign in</a>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <span>© 2026 RouteBridge</span>
        <span>Built for Lagos, Abuja, Kano and Ibadan</span>
      </footer>
    </div>
  );
}
