# Build context is the repo ROOT (see docker-compose `context: ../../`) so the
# pnpm workspace lockfile is available for a reproducible, frozen install.
FROM node:20-alpine AS build
# corepack installs the EXACT pnpm pinned in the root package.json
# (`packageManager: pnpm@9.12.0`) — one source of truth, matches dev + CI.
RUN corepack enable
WORKDIR /app

# Workspace manifests + lockfile first (cached layer). All JS workspace members'
# package.json must be present for `--frozen-lockfile` to validate the lockfile.
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY apps/studio/package.json apps/studio/package.json
COPY infra/cdk/package.json infra/cdk/package.json

RUN pnpm install --frozen-lockfile --filter @pdlcflow/studio...

# Studio source, then build just the studio package.
COPY apps/studio apps/studio
RUN pnpm --filter @pdlcflow/studio build

FROM nginx:alpine
COPY --from=build /app/apps/studio/dist /usr/share/nginx/html
COPY apps/studio/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
