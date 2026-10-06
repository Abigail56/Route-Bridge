# RouteBridge web console

First frontend slice for the RouteBridge operations console. It provides the dashboard shell, delivery operations table, filters, live-driver visual, COD summary, job detail drawer, and an SSE live-stream status indicator. Demo data is intentionally local until the authenticated API client is connected.

## Run

```bash
cd apps/web
npm install
npm run dev
```

For live SSE status, copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_ROUTE_BRIDGE_TENANT_ID`.
