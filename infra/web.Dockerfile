# Next.js web/BFF tier — multi-stage build for the npm-workspaces monorepo.
# Build context is the repository root.

FROM node:22-alpine AS builder
WORKDIR /app

# Install workspace dependencies (leverage layer caching on manifests).
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/shared-types/package.json packages/shared-types/package.json
RUN npm ci

# Build the web app (copy-cesium runs as part of the build script).
COPY . .
RUN npm run build --workspace apps/web

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
# Next.js standalone output is rooted at the monorepo (outputFileTracingRoot).
COPY --from=builder /app/apps/web/.next/standalone ./
COPY --from=builder /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder /app/apps/web/public ./apps/web/public
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
