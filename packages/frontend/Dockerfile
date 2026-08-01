# syntax=docker/dockerfile:1.7

ARG NODE_VERSION=22.23.1

FROM node:${NODE_VERSION}-bookworm-slim AS dependencies
WORKDIR /workspace

ENV NEXT_TELEMETRY_DISABLED=1

# Copy manifests first so dependency installation remains cacheable. The
# Docker build context is the monorepo root; only the active frontend and its
# shared workspace dependency are installed.
COPY package.json package-lock.json ./
COPY packages/frontend/package.json ./packages/frontend/package.json
COPY packages/shared/package.json ./packages/shared/package.json
RUN npm ci --workspace @elderly-care/frontend --include-workspace-root=false

FROM dependencies AS builder

COPY tsconfig.base.json ./tsconfig.base.json
COPY packages/shared ./packages/shared
COPY packages/frontend ./packages/frontend

# NEXT_PUBLIC values are public by definition and are compiled into browser
# assets. Never add OAuth secrets, tokens, or server credentials as build args.
ARG NEXT_PUBLIC_CONSENT_POLICY_VERSION=""
ARG NEXT_PUBLIC_WS_URL=""
ENV NEXT_PUBLIC_CONSENT_POLICY_VERSION=${NEXT_PUBLIC_CONSENT_POLICY_VERSION} \
    NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}

RUN npm run build --workspace @elderly-care/frontend

FROM node:${NODE_VERSION}-bookworm-slim AS runner
WORKDIR /app

LABEL io.kinsun.artifact="frontend"

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs --create-home nextjs

COPY --from=builder --chown=nextjs:nodejs /workspace/packages/frontend/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /workspace/packages/frontend/.next/static ./packages/frontend/.next/static
COPY --from=builder --chown=nextjs:nodejs /workspace/packages/frontend/public ./packages/frontend/public

RUN mkdir -p /app/packages/frontend/.next/cache \
    && chown -R nextjs:nodejs /app/packages/frontend/.next

# ECS Fargate mounts this exact absolute path. Declaring it after ownership is
# established preserves the image directory's nextjs ownership for the mount.
VOLUME ["/app/packages/frontend/.next/cache"]

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/health').then((response) => { if (!response.ok) process.exit(1); }).catch(() => process.exit(1));"]

CMD ["node", "packages/frontend/server.js"]
