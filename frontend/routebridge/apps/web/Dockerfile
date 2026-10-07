FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# NEXT_PUBLIC_* values are inlined at build time
ARG NEXT_PUBLIC_API_BASE_URL
ARG API_INTERNAL_URL
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ARG NEXT_PUBLIC_SESSION_MAX_HOURS
ARG NEXT_PUBLIC_SESSION_IDLE_MINUTES
ARG NEXT_PUBLIC_MAP_PROVIDER
ARG NEXT_PUBLIC_MAP_API_KEY
ARG NEXT_PUBLIC_MAP_TILE_URL
ARG NEXT_PUBLIC_MAP_ATTRIBUTION
ENV API_INTERNAL_URL=$API_INTERNAL_URL NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY NEXT_PUBLIC_SESSION_MAX_HOURS=$NEXT_PUBLIC_SESSION_MAX_HOURS NEXT_PUBLIC_SESSION_IDLE_MINUTES=$NEXT_PUBLIC_SESSION_IDLE_MINUTES NEXT_PUBLIC_MAP_PROVIDER=$NEXT_PUBLIC_MAP_PROVIDER NEXT_PUBLIC_MAP_API_KEY=$NEXT_PUBLIC_MAP_API_KEY NEXT_PUBLIC_MAP_TILE_URL=$NEXT_PUBLIC_MAP_TILE_URL NEXT_PUBLIC_MAP_ATTRIBUTION=$NEXT_PUBLIC_MAP_ATTRIBUTION
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup -S app && adduser -S app -G app
# standalone output = server.js plus only the node_modules it needs
COPY --from=build --chown=app:app /app/.next/standalone ./
COPY --from=build --chown=app:app /app/.next/static ./.next/static
COPY --from=build --chown=app:app /app/public ./public
USER app
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD wget -qO- http://127.0.0.1:3000/driver >/dev/null || exit 1
CMD ["node", "server.js"]
