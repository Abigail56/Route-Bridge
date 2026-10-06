# Driver app end-to-end test

Open the app at `http://localhost:3000` (the API's CORS list allows that origin by default).
Drives the real driver PWA in headless Chromium against a running API + web server: token sign-in, going offline
mid-delivery, ordered sync on reconnect, server-verified OTP, photo upload, encrypted-at-rest checks, and the offline
app shell. 17 checks.

```bash
# 1. API (throwaway SQLite db + media folder)
cd backend/apps/api
ROUTEBRIDGE_DATABASE_URL=sqlite:///./e2e.db ROUTEBRIDGE_DRIVER_TOKEN_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(40))") \
ROUTEBRIDGE_MEDIA_DIR=../../../frontend/routebridge/apps/web/media PYTHONPATH=src uvicorn routebridge.main:app --port 8000 &

# 2. Web (production build, standalone server - the same way the Docker image runs it)
cd frontend/routebridge/apps/web && npm run build \n  && cp -r .next/static .next/standalone/.next/static && cp -r public .next/standalone/public \n  && PORT=3000 HOSTNAME=0.0.0.0 node .next/standalone/server.js &

# 3. Test
cd frontend/routebridge/apps/web/e2e && npm install && npx playwright install --with-deps chromium && RB_MEDIA_DIR=../media npm test
```
