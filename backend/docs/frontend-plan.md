# RouteBridge Frontend Plan

## 1. Frontend strategy

RouteBridge should have three interfaces:

1. **Operations console** for tenant owners, dispatchers, operations managers, merchants, and finance users.
2. **Driver application** for Android-first field execution and offline synchronization.
3. **Customer tracking page** for tokenized delivery visibility.

Build the operations console first because it is the control center for the backend workflow. Build the driver application after the API state machine and mobile-sync contract are stable. Build the customer page as a small, focused surface after delivery status and notification contracts are established.

## 2. Frontend technology

Recommended web stack:

- Next.js
- TypeScript
- App Router
- Tailwind CSS or a small design-system layer
- TanStack Query for server state and cache invalidation
- React Hook Form for forms
- Zod for client-side validation aligned with API schemas
- MapLibre or a provider adapter for maps
- Playwright for browser acceptance tests
- Vitest for component and utility tests

The frontend should consume the FastAPI OpenAPI contract rather than duplicating backend business rules. Generate or maintain typed API clients from OpenAPI where practical.

Recommended mobile stack:

- React Native or Kotlin
- SQLite/Room encrypted local event queue
- Stable device-generated event IDs
- Background synchronization
- Compressed photo uploads
- Explicit accepted, duplicate, and rejected event states

## 3. Operations-console navigation

The primary web navigation should include:

- Overview
- Dispatch board
- Orders
- Delivery jobs
- Drivers
- Customers
- Merchants
- Service zones
- Exceptions
- Reconciliation
- Notifications
- Reports
- Settings
- Audit history

The navigation must be filtered by role and tenant scope.

## 4. Main screens

### Overview dashboard

Show:

- Jobs today
- Unassigned jobs
- In-progress jobs
- Delivered jobs
- Failed attempts
- Delayed jobs
- COD exceptions
- Sync-lag alerts
- Driver availability
- On-time delivery rate
- First-attempt success rate

The dashboard should expose operational exceptions first. A map is useful, but a map alone is not an operations system.

### Dispatch board

The dispatch board is the most important web screen.

It should support:

- Columns or grouped views by delivery state
- Filters for operating area, service zone, window, priority, driver, confidence, and exception
- Assignment and reassignment
- Job detail drawer
- Driver availability panel
- Landmark and map-pin display
- Delivery notes
- Customer contact action
- Failed-attempt reason
- Route or batch grouping
- Manual override
- Optimistic updates with rollback on API failure

### Orders screen

Show:

- External reference
- Merchant
- Customer
- Phone
- Address and landmark
- Amount
- COD amount
- Order status
- Delivery status
- Created time
- Location confidence
- Import source

Actions:

- Create order
- Import CSV
- Open delivery job
- Correct location with history
- Resend notification
- View audit timeline

### Order creation form

The form should be divided into:

1. Merchant and external reference
2. Customer details
3. Address and landmark
4. Map pin and confidence
5. Delivery window and priority
6. Payment and COD
7. Notes and availability

The form must display a warning when the location is unverified or the COD amount differs from the order total.

### CSV import screen

The import flow should be:

```text
Select file
  → Validate columns
      → Preview rows
          → Show row errors
              → Confirm import
                  → Show created orders
                      → Show failed rows for correction
```

Never silently discard invalid rows.

### Delivery-job detail

Show:

- Current state
- Full transition timeline
- Assigned driver
- Customer and merchant
- Map and delivery location
- Landmark and notes
- Attempts
- Proof of delivery
- Payment record
- Reconciliation status
- Notifications
- Audit events

### Driver screen

Show:

- Driver status
- Fleet type
- Current assignment
- Jobs completed
- Failed attempts
- Proof completeness
- Sync lag
- Last device activity
- Cash or COD outstanding

### Exceptions screen

Group exceptions by:

- Unassigned
- Low location confidence
- Recipient unreachable
- Failed attempt
- Late delivery
- Missing proof
- COD variance
- Unmatched transfer
- Provider failure
- Mobile sync rejection

Every exception should have an owner, status, notes, and next action.

### Reconciliation screen

Show:

- Expected amount
- Collected amount
- Variance
- Payment method
- Provider reference
- Driver or partner
- Status
- Created time
- Resolution note

Actions should require appropriate finance permissions. Resolved items must remain visible in audit history.

### Reports screen

Initial reports:

- Deliveries by region and zone
- On-time delivery
- First-attempt success
- Failed-attempt reasons
- Cost per stop
- Driver performance
- Proof completeness
- COD variance
- Reconciliation backlog
- Notification delivery
- Mobile synchronization lag

## 5. Roles and permissions

### Tenant owner

Full tenant access, configuration, users, operations, finance, reports, and audit history.

### Administrator

Tenant configuration and users, but financial permissions should be explicitly granted.

### Dispatcher

Orders, dispatch board, drivers, delivery jobs, exceptions, and notifications. No settlement approval unless granted.

### Finance user

Payments, reconciliation, refunds, settlement exports, and financial reports. No driver credential administration by default.

### Operations manager

Dispatch, drivers, jobs, exceptions, proof, and performance reports.

### Merchant user

Own merchant orders, statuses, proofs, and reports. No access to other merchants in the same tenant unless explicitly granted.

### Read-only viewer

Read-only operational dashboards and reports.

### Driver

Only assigned jobs and permitted delivery actions through the mobile application.

## 6. Frontend state rules

The frontend must not invent state transitions. It should render the backend transition contract.

For every action:

1. Check whether the action is allowed by the current state.
2. Send the API request.
3. Invalidate or update affected queries.
4. Show the resulting state from the server.
5. Display errors without pretending the action succeeded.

For mobile events:

```text
Local event queued
  → Sending
      → Accepted
      → Duplicate
      → Rejected
      → Retry required
```

A rejected mobile event must remain visible to the driver or support operator.

## 7. Frontend folder structure

```text
apps/web/
├── app/
│   ├── (auth)/
│   ├── (console)/
│   │   ├── overview/
│   │   ├── dispatch/
│   │   ├── orders/
│   │   ├── deliveries/
│   │   ├── drivers/
│   │   ├── customers/
│   │   ├── merchants/
│   │   ├── exceptions/
│   │   ├── reconciliation/
│   │   ├── notifications/
│   │   ├── reports/
│   │   └── settings/
│   ├── track/[token]/
│   ├── layout.tsx
│   └── providers.tsx
├── components/
│   ├── ui/
│   ├── charts/
│   ├── maps/
│   ├── orders/
│   ├── dispatch/
│   ├── deliveries/
│   ├── drivers/
│   ├── reconciliation/
│   └── navigation/
├── features/
│   ├── auth/
│   ├── orders/
│   ├── dispatch/
│   ├── deliveries/
│   ├── reconciliation/
│   └── reports/
├── lib/
│   ├── api-client.ts
│   ├── query-client.ts
│   ├── permissions.ts
│   ├── formatters.ts
│   └── errors.ts
├── hooks/
├── types/
├── public/
└── tests/
```

## 8. Web build order

### Web slice 1: authenticated shell

Build the layout, navigation, tenant context, role-aware navigation, loading states, error boundary, and API client.

### Web slice 2: orders

Build order list, order detail, create order, and CSV import preview.

### Web slice 3: dispatch

Build the dispatch board, assignment, job detail, state transitions, driver panel, and exceptions.

### Web slice 4: delivery evidence

Build proof display, attempt timeline, photos, signatures, OTP status, and customer tracking.

### Web slice 5: finance

Build payment detail, reconciliation list, variance filters, resolution workflow, and exports.

### Web slice 6: reports and settings

Build metrics, service zones, rate cards, notification templates, operating-area configuration, and audit history.

## 9. First frontend vertical slice

The first web implementation should cover one complete workflow:

```text
Open orders
  → Create order
      → View order and delivery job
          → Assign driver
              → Change delivery state
                  → View proof
                      → View COD payment
                          → View reconciliation result
```

This should be connected to the existing backend before building decorative dashboards.

## 10. Frontend testing

### Unit tests

Test:

- Currency formatting
- Phone formatting
- Status labels
- Permission checks
- Transition availability
- CSV validation display
- Variance formatting
- Location-confidence labels

### Integration tests

Test:

- Order creation
- Tenant switching
- Driver assignment
- State transition errors
- Proof display
- COD exception display
- Reconciliation resolution
- Notification retry states

### Browser acceptance tests

Test:

1. Dispatcher creates an order.
2. Dispatcher assigns a driver.
3. Driver or test API moves the job through states.
4. Proof appears in the console.
5. COD exact match appears as matched.
6. COD variance appears as exception.
7. Finance user resolves the exception.
8. Unauthorized roles cannot access restricted screens.

## 11. Visual and operational principles

- Exceptions must be more visible than decorative maps.
- Every asynchronous action needs a loading, success, and error state.
- Never hide location confidence.
- Never present a map pin as proof that the address is correct.
- Never present delivery proof as proof of payment remittance.
- Use clear Nigerian currency formatting with NGN.
- Use phone-friendly tables and cards.
- Avoid dense screens that require a large monitor.
- Support slow networks with skeletons, pagination, retry actions, and cached read data.
- Preserve server state as the source of truth.
- Keep operational language clear for dispatchers and drivers.

## 12. Frontend acceptance criteria

The first frontend release is ready for pilot when:

- A dispatcher can create or import an order.
- A dispatcher can see location confidence and delivery notes.
- A dispatcher can assign and reassign a driver.
- The console renders valid and invalid state transitions correctly.
- A user can see delivery attempts and proof.
- A finance user can see exact, under, and over COD outcomes.
- Tenant users cannot see another tenant's records.
- Role restrictions are enforced in both navigation and API responses.
- CSV errors are visible by row.
- Slow or failed requests do not create false success states.
- The interface works on desktop and tablet widths.
- Browser acceptance tests pass against a staging API.
