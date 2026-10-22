// The public front page: what signed-out visitors see at "/". Signed-in people never see it (app/page.tsx shows their console).
// The shop plans are read from the API (GET /public/plans/shops, from config/plans.py), so the prices shown are the prices charged.
// No internal how-to-join steps: the sign-up screens guide people through that.
import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../lib/api';

type PublicPlan = { key: string; name: string; price_ngn: number; orders_per_month: number | null; blurb: string };

function usePlans(): { trialDays: number; plans: PublicPlan[] } | null {
  const [data, setData] = useState<{ trialDays: number; plans: PublicPlan[] } | null>(null);
  useEffect(() => {
    let live = true;
    fetch(`${API_BASE_URL}/api/v1/public/plans/shops`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => { if (live && body?.plans?.length) setData({ trialDays: body.trial_days, plans: body.plans }); })
      .catch(() => undefined); // the API may be waking up: the section simply stays hidden
    return () => { live = false; };
  }, []);
  return data;
}

const naira = (amount: number) => `₦${amount.toLocaleString('en-NG')}`;

// The hero's photos: each one fades in and zooms slowly, then the next takes over. `small` is a lighter copy for phones;
// `position` / `smallPosition` keep the important part (the people) in view when the photo is cropped on wide screens / phones.
// Add a photo here to add a slide.
const HERO_PHOTOS: { src: string; small: string; position: string; smallPosition: string }[] = [
  { src: '/routebridge-bg.jpg', small: '/routebridge-bg-sm.jpg', position: '72% 45%', smallPosition: '78% center' },
  { src: '/routebridge-hero-road.jpg', small: '/routebridge-hero-road-sm.jpg', position: 'center 8%', smallPosition: '45% center' },
  { src: '/routebridge-hero-handover.jpg', small: '/routebridge-hero-handover-sm.jpg', position: 'center 30%', smallPosition: '62% center' },
];
const SLIDE_SECONDS = 7;

function HeroSlides() {
  // `leaving` keeps the previous photo's zoom running while it fades out, so it never snaps back mid-fade
  const [{ active, leaving }, setSlides] = useState({ active: 0, leaving: -1 });
  useEffect(() => {
    if (HERO_PHOTOS.length < 2) return;
    const timer = setInterval(() => setSlides(({ active: current }) => ({ active: (current + 1) % HERO_PHOTOS.length, leaving: current })), SLIDE_SECONDS * 1000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="lp-hero-slides" aria-hidden="true">
      {HERO_PHOTOS.map((photo, index) => (
        <span
          key={photo.src}
          className={`lp-hero-slide${index === active ? ' is-active' : index === leaving ? ' is-leaving' : ''}${HERO_PHOTOS.length < 2 ? ' is-only' : ''}`}
          style={{ '--photo': `url('${photo.src}')`, '--photo-sm': `url('${photo.small}')`, '--photo-pos': photo.position, '--photo-pos-sm': photo.smallPosition } as React.CSSProperties}
        />
      ))}
    </div>
  );
}

// shown publicly in "Get in touch" and the footer; the phone number is also the WhatsApp number
const CONTACT_EMAIL = 'chukwuabigail307@gmail.com';
const CONTACT_PHONE = { display: '0906 046 1720', tel: '+2349060461720', whatsapp: '2349060461720' };

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
  home: 'M3 11 12 4l9 7M5 10v10h14V10M10 20v-6h4v6',
  mail: 'M3 6h18v12H3zM3 7l9 6 9-6',
  call: 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2',
  chat: 'M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12z',
  target: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12h.01',
  handshake: 'M3 12l4-4 4 2 3-3 7 7-4 4-3-3-2 2-3-3-2 2z',
};
type IconName = keyof typeof icons;

function LandingIcon({ name }: { name: IconName }) {
  return <svg className="lp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={icons[name]} /></svg>;
}

// Each problem says what happens, why it costs money, and (fix) what RouteBridge does about it.
const problems: { icon: IconName; title: string; text: string; fix: string }[] = [
  { icon: 'inbox', title: 'Scattered orders', text: 'Orders arrive through WhatsApp chats, Instagram DMs, phone calls and notebooks. Nothing is in one list, so orders get missed, sent twice, or forgotten until the customer calls to complain.', fix: 'Shops place every order in one portal, and it appears on one board.' },
  { icon: 'pin', title: 'Vague addresses', text: 'Many addresses are directions, not street numbers: “opposite the blue church, after the second junction.” Riders burn fuel and time calling customers to find the gate, and some parcels come back undelivered.', fix: 'Each order carries a landmark, the customer’s phone and a map pin, and the customer can correct the location from their tracking link.' },
  { icon: 'eye', title: 'Blind dispatch', text: 'Parcels are handed out by phone and chat. Once riders leave, nobody knows who has which parcel, where they are, or when it will arrive, so shops and customers keep calling to ask.', fix: 'Every order is given to a named rider on a dispatch board and followed live on a map.' },
  { icon: 'shield', title: 'Weak proof', text: 'A rider can mark a parcel “delivered” when it wasn’t, or hand it to the wrong person. With no proof, the shop ends up arguing with its customer, and someone loses the money.', fix: 'A delivery only counts when the customer gives the rider a one-time code. A photo alone is not enough.' },
  { icon: 'cash', title: 'Leaking cash', text: 'Riders collect cash on delivery and pay it in later. Working out who paid what, shop by shop, is done by hand, so mistakes and missing money are hard to spot.', fix: 'The rider records the amount at the door, and every shop gets a clear statement of cash collected, fees and claims.' },
  { icon: 'signal', title: 'Patchy data', text: 'Mobile signal drops on many roads and inside many buildings. Apps that need the internet all the time freeze in the middle of a delivery, and updates are lost.', fix: 'Our rider app saves every step on the phone and sends it in the right order when signal returns.' },
];

const steps = [
  { title: 'The shop places the order', text: 'From its own portal, with the customer’s landmark, phone and zone.' },
  { title: 'A driver is assigned', text: 'On the Dispatch board, or automatically to a free driver in that zone.' },
  { title: 'The customer watches it come', text: 'A tracking link shows the rider on a map while the parcel is on the way.' },
  { title: 'A code confirms the handover', text: 'The delivery completes only when the customer’s code checks out. Then the cash is settled.' },
];

const audiences: { icon: IconName; title: string; text: string }[] = [
  { icon: 'store', title: 'Shops and online sellers', text: 'Place delivery orders in minutes, follow every parcel live, and see exactly what you are owed from cash on delivery.' },
  { icon: 'home', title: 'Customers', text: 'Know when your parcel is coming, watch the rider on a map, and hand over a code only when the parcel is in your hands.' },
  { icon: 'team', title: 'Drivers', text: 'See only your own jobs, get an alert when one is assigned, and keep working even when the signal drops.' },
];

export function Landing() {
  const shopPlans = usePlans();
  return (
    <div className="lp">
      <header className="lp-hero">
        <HeroSlides />
        <nav className="lp-nav" aria-label="Main">
          <a className="lp-brand" href="/"><span className="brand-mark" aria-hidden="true" /><strong>RouteBridge</strong></a>
          <div className="lp-nav-links">
            <a href="#about">About us</a>
            <a href="#how">How it works</a>
            <a href="#who">Who it’s for</a>
            <a href="#plans">Plans</a>
            <a href="#contact">Contact</a>
          </div>
          <div className="lp-nav-actions">
            <a className="lp-btn lp-btn-ghost" href="/sign-in">Sign in</a>
            <a className="lp-btn lp-btn-solid" href="/sign-up">Get started</a>
          </div>
        </nav>
        <div className="lp-hero-copy">
          <p className="lp-eyebrow">Last-mile delivery for Nigeria</p>
          <h1>Every order in one place. Every delivery proven.</h1>
          <p className="lp-lead">RouteBridge Logistics delivers for shops across Nigeria: every order tracked from pickup to doorstep, and every handover confirmed by the customer.</p>
          <div className="lp-hero-actions">
            <a className="lp-btn lp-btn-solid lp-btn-lg" href="/sign-up">Get started</a>
            <a className="lp-btn lp-btn-ghost lp-btn-lg" href="/sign-in">Sign in</a>
          </div>
        </div>
      </header>

      <main>
        <section className="lp-section" id="about" aria-labelledby="lp-about">
          <p className="lp-kicker">About us</p>
          <h2 id="lp-about">A Nigerian delivery company that proves every delivery</h2>
          <div className="lp-about">
            <p>RouteBridge Logistics is a last-mile delivery company for Nigeria. We pick up parcels from shops and online sellers and bring them to their customers&apos; doors, with cash on delivery collected and settled properly.</p>
            <p>We built our own platform to do it well. Shops place orders from their own portal, our riders work from an app that keeps going without signal, customers follow their parcel live, and a delivery only counts as done when the customer confirms it with a one-time code.</p>
          </div>
          <p className="lp-mission-text" id="mission"><b>Our mission:</b> to make every delivery in Nigeria one people can trust. We want any shop in Nigeria to send a parcel and know it will arrive, that the customer received it, and that the money comes back. No guesswork, no lost cash, no “the rider said it was delivered”.</p>
        </section>

        <section className="lp-section lp-band" aria-labelledby="lp-problem">
          <p className="lp-kicker">The problem</p>
          <h2 id="lp-problem">Same-city delivery in Nigeria runs on calls and trust</h2>
          <p className="lp-problem-intro">Shops lose money on delivery every day, rarely through one big failure. It is six small ones that add up.</p>
          <div className="lp-grid lp-grid-3">
            {problems.map((item) => (
              <article className="lp-card lp-problem" key={item.title}><LandingIcon name={item.icon} /><h3>{item.title}</h3><p>{item.text}</p><p className="lp-fix"><b>How we fix it:</b> {item.fix}</p></article>
            ))}
          </div>
        </section>

        <section className="lp-section" id="how" aria-labelledby="lp-how">
          <p className="lp-kicker">How it works</p>
          <h2 id="lp-how">From the shop’s order to cash in the bank</h2>
          <ol className="lp-steps">
            {steps.map((step, index) => (
              <li key={step.title}><span className="lp-step-number">{index + 1}</span><h3>{step.title}</h3><p>{step.text}</p></li>
            ))}
          </ol>
        </section>

        <section className="lp-section lp-band" id="who" aria-labelledby="lp-who">
          <p className="lp-kicker">Who it’s for</p>
          <h2 id="lp-who">One platform, a screen for everyone</h2>
          <div className="lp-grid lp-grid-3">
            {audiences.map((item) => (
              <article className="lp-card lp-card-top" key={item.title}><LandingIcon name={item.icon} /><h3>{item.title}</h3><p>{item.text}</p></article>
            ))}
          </div>
        </section>

        {shopPlans && <section className="lp-section" id="plans" aria-labelledby="lp-plans">
          <p className="lp-kicker">Plans for shops</p>
          <h2 id="lp-plans">Start free for {shopPlans.trialDays} days, then pick a monthly plan</h2>
          <div className="lp-plan-grid">
            {shopPlans.plans.map((plan) => (
              <article className={`lp-plan${plan.key === 'trial' ? ' lp-plan-trial' : ''}`} key={plan.key}>
                <h3>{plan.name}</h3>
                <p className="lp-plan-price">{plan.price_ngn === 0 ? <>Free<small> for {shopPlans.trialDays} days</small></> : <>{naira(plan.price_ngn)}<small> / month</small></>}</p>
                <p className="lp-plan-orders">{plan.orders_per_month ? `Up to ${plan.orders_per_month.toLocaleString('en-NG')} orders a month` : 'Unlimited orders'}</p>
                <p className="lp-plan-blurb">{plan.blurb}</p>
                <a className="lp-btn lp-btn-outline" href="/sign-up">{plan.price_ngn === 0 ? 'Start free' : 'Get started'}</a>
              </article>
            ))}
          </div>
          <p className="lp-plan-note">Every plan includes live tracking, delivery codes, cash-on-delivery statements and claims. Prices are in naira. Deliveries already on the road are never stopped because of billing.</p>
        </section>}

        <section className="lp-section lp-band" id="contact" aria-labelledby="lp-contact">
          <p className="lp-kicker">Get in touch</p>
          <h2 id="lp-contact">Questions? Talk to us</h2>
          <div className="lp-contact">
            <p>Want RouteBridge Logistics to deliver for your shop, or have a question about an order or a payment? Call, chat on WhatsApp or send us an email and we will get back to you.</p>
            <div className="lp-contact-cards">
              {/* one number for calls and WhatsApp: one card, two buttons */}
              <div className="lp-contact-card lp-contact-phone">
                <LandingIcon name="call" />
                <span><small>Call / WhatsApp</small><b>{CONTACT_PHONE.display}</b></span>
                <span className="lp-contact-actions">
                  <a className="lp-btn lp-btn-outline" href={`tel:${CONTACT_PHONE.tel}`}>Call</a>
                  <a className="lp-btn lp-btn-outline" href={`https://wa.me/${CONTACT_PHONE.whatsapp}?text=${encodeURIComponent('Hello RouteBridge Logistics, ')}`} target="_blank" rel="noopener noreferrer">WhatsApp</a>
                </span>
              </div>
              <a className="lp-contact-card" href={`mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent('RouteBridge enquiry')}`}>
                <LandingIcon name="mail" />
                <span><small>Email us</small><b>{CONTACT_EMAIL.split('@')[0]}@<wbr />{CONTACT_EMAIL.split('@')[1]}</b></span>
              </a>
            </div>
          </div>
        </section>

        <section className="lp-cta" aria-labelledby="lp-cta">
          <h2 id="lp-cta">Ready to send your first delivery?</h2>
          <p>Create your account. It takes a minute.</p>
          <div className="lp-hero-actions">
            <a className="lp-btn lp-btn-solid lp-btn-lg" href="/sign-up">Get started</a>
            <a className="lp-btn lp-btn-ghost lp-btn-lg" href="/sign-in">Sign in</a>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <span>© 2026 RouteBridge</span>
        <span><a href={`tel:${CONTACT_PHONE.tel}`}>{CONTACT_PHONE.display}</a> · <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a></span>
      </footer>
    </div>
  );
}
