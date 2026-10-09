# RouteBridge Logistics: slide outline

A 14-slide deck for a presentation or interview walk-through (about 10 minutes). Speaker notes are under each slide.

## 1. Title
**RouteBridge Logistics: last-mile delivery for Nigeria**
Your name, date, link to the live demo.
*Say:* one sentence: "A platform that gets parcels to the right door, with the right cash, even on a bad network."

## 2. The problem
- Vague addresses ("the yellow gate after the church"), so riders get lost
- Patchy mobile data, so apps break mid-delivery
- Cash on delivery goes missing and shops argue about what they are owed
- Customers cannot see where the parcel is, so calls pile up
- Wrong person or fake "delivered" marks

## 3. The solution in one picture
Four surfaces on one system: operations console, driver app (PWA), merchant portal, customer tracking page.
*Show:* a screenshot of each.

## 4. How one delivery flows
Order, assign rider, push alert, en route, arrived, delivery code, proof and cash, reconciliation, statement.
*Show:* a simple left-to-right flow diagram.

## 5. Key features
- Landmark and zone addressing with a location-confidence score
- Offline driver app with background sync
- Live tracking link for the customer
- Delivery code, photo and signature proof
- Cash reconciliation, merchant statements and claims
- Optional automatic assignment, billing plans, audit log

## 6. Architecture
Browser or phone, Next.js, FastAPI, then PostgreSQL/PostGIS, Redis and MinIO. Workers (outbox, notifications, maintenance). Clerk for sign-in. Outside services: Twilio, Resend, Paystack, push.

## 7. Backend stack and why
FastAPI, SQLModel/SQLAlchemy, Alembic, PostgreSQL + PostGIS, Redis, MinIO, PyJWT, httpx, pywebpush, pydantic-settings, pytest. One line of reasoning each.

## 8. Frontend stack and why
Next.js 14, React 18, TypeScript, Clerk, Leaflet, qrcode, service worker + IndexedDB, vitest, ESLint.

## 9. Security and multi-tenancy
- `tenant_id` on every row, role check on every route
- Merchant users fenced to their own portal
- Hashed, expiring, attempt-limited delivery codes
- Secrets only in env files, production check refuses unsafe settings

## 10. Reliability patterns
Outbox pattern, idempotency keys, circuit breaker, locked idempotent migrations, backup-restore test, Prometheus/Grafana monitoring.

## 11. Delivery-code relay (the newest feature)
Rider taps "Text the customer a delivery code", a card and bell alert appear on the dashboard, staff send it by WhatsApp, text or call, then press "Mark as sent". Why: the Twilio trial has no sender. How to switch later: set `OTP_DELIVERY=sms`.

## 12. Testing and quality
182 backend tests, 43 frontend tests, type-check and lint, browser checks of the real screens, migration-from-empty test.

## 13. Honest limits and next steps
Trial SMS, development Clerk keys (no domain yet), PWA not native, untested at scale. Next: native Android, live SMS and payments, load test, security review, local languages.

## 14. Questions
Link to repo and live demo. Keep the interview Q&A (`docs/project-guide.md`, section 12) open.
