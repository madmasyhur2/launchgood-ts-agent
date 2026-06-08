# =============================================================================
# LaunchGood T&S Agent — Frontend Dockerfile (Next.js)
# =============================================================================
# Multi-stage build:
#   Stage 1 (deps):    Install node_modules
#   Stage 2 (builder): Build the Next.js production bundle (standalone mode)
#   Stage 3 (runtime): Minimal image serving the standalone output
# =============================================================================

# ---- Stage 1: install dependencies ----
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ---- Stage 2: build ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copy installed modules from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source
COPY . .

# NEXT_PUBLIC_* vars must be present at BUILD time (embedded by webpack)
# Pass via --build-arg when running docker build, or set in CI/CD
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Build with standalone output (smallest possible runtime image)
RUN npm run build

# ---- Stage 3: runtime ----
FROM node:20-alpine AS runtime

# Security: run as non-root
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Copy only the built standalone output and static assets
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD wget -qO- http://localhost:3000 || exit 1

CMD ["node", "server.js"]
