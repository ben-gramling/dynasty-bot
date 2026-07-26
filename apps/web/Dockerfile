# dynasty-bot web — two-stage standalone Next.js build (tomato dashboard
# pattern: node:20-slim, npm ci -> next build, runner copies .next/standalone).
# node:20-slim satisfies Next 16 (requires Node >= 20.9) and is the exact base
# tomato runs Next 16.2.x on in production.
#
# Build context is the REPO ROOT (CI: docker build -f apps/web/Dockerfile .).
# Docker is not available locally — this image builds in CI only.

FROM node:20-slim AS builder
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ .
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
# Explicit where tomato is implicit: Next's standalone server.js binds
# localhost unless HOSTNAME is set, and the ALB health check reaches the
# container over the awsvpc ENI — it must listen on all interfaces.
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
# No public/ copy: apps/web has no public directory (static assets like
# icon.svg live under src/app and are bundled by Next).
EXPOSE 3000
CMD ["node", "server.js"]
