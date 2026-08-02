# Core API

`services/core-api` contains the canonical FastAPI domain and authorization
service. It deliberately has two container entry points that use the same
`pyproject.toml` and `uv.lock`:

| File | Purpose | Default command |
| --- | --- | --- |
| `Dockerfile` | Non-root, one-shot schema migration job | migrate + runtime-role reconciliation |
| `Dockerfile.api` | Long-running production API | `uvicorn app.main:app` |

Do not run Alembic from the API container startup path. Deployment must finish
the migration job successfully before shifting traffic to a new API revision.

## Build

Run these commands from this directory:

```powershell
docker build --file Dockerfile.api --tag kinsun-core-api:local .
docker build --file Dockerfile --tag kinsun-core-api-migrate:local .
```

Both builds are lockfile-enforced. A stale `uv.lock` causes the build to stop.
The API image copies only `app/` and its production dependencies; tests,
developer environments, and `.env*` files are excluded from the Docker context.

## Runtime configuration

`Dockerfile.api` defaults `APP_ENV=production`, which disables OpenAPI
documentation and prevents the application from reading a local `.env` file.
Supply credentials at runtime through ECS Secrets Manager or another runtime
secret mechanism; never put them in a build argument, image, or committed env
file.

The shared Python entrypoint supports two database configuration paths:

1. If `DATABASE_URL` is present, it is preserved unless the TLS option described
   below must be added. The API expects the `postgresql+asyncpg://` scheme;
   Alembic accepts the existing migration configuration.
2. Otherwise, provide `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME`, and
   `DB_PASSWORD`. The entrypoint percent-encodes the username, password, and
   database name, then creates an asyncpg URL for the API or a psycopg URL for
   the migration job.

The entrypoint never prints the URL or component values. This lets ECS inject
Aurora username/password fields directly from Secrets Manager without making
IaC reconstruct or expose a credential-bearing URL.

Staging ECS tasks must set `DB_SSLMODE=require`. The entrypoint emits the
driver-specific query option (`ssl=require` for SQLAlchemy/asyncpg and
`sslmode=require` for psycopg), rejects conflicting/weaker explicit modes, and
leaves local development unchanged when the setting is absent.

The migration image additionally requires `DB_RUNTIME_USERNAME=kinsun_app` and
`DB_RUNTIME_PASSWORD` from the retained runtime credential secret. It validates
both secrets before mutation, runs `alembic upgrade head` with the Aurora admin
credential, then creates or reconciles the runtime LOGIN role. The role gets
only database CONNECT, schema USAGE, table SELECT/INSERT/UPDATE/DELETE, enum or
domain type USAGE, and sequence USAGE/SELECT for current and future
`eldercare_ai` objects. Unexpected ownership or role membership fails closed.
The long-lived Core task receives only the runtime secret; only the one-shot
migration execution role may read both admin and runtime secrets.

Local development defaults `DB_POOL_MODE=queue`, using `DB_POOL_SIZE` and
`DB_MAX_OVERFLOW`. Aurora staging tasks should set `DB_POOL_MODE=null`; in that
mode SQLAlchemy receives `NullPool` and no queue-pool sizing arguments, avoiding
persistent idle application connections that work against Aurora auto-pause.
`DB_CONNECT_TIMEOUT_SECONDS` bounds each asyncpg connection attempt and
`DB_RECOVERY_TIMEOUT_SECONDS` bounds request/startup readiness recovery.

If Aurora is unavailable during startup, the service stays in degraded mode.
The next database-backed request starts one bounded connectivity recovery; all
overlapping requests await that same attempt. A later request may retry after a
failure. There is no background or periodic recovery probe, and `/health`
remains database-independent.

When Cognito authentication is enabled, also provide `COGNITO_REGION`,
`COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`, and a minimum 32-byte
`FAMILY_INVITATION_HMAC_SECRET` at runtime.

For a local smoke test, create a git-ignored `.env.runtime.local`, then run:

```powershell
docker run --rm --name kinsun-core-api `
  --env-file .env.runtime.local `
  --publish 8000:8000 `
  --read-only `
  --tmpfs /tmp:rw,noexec,nosuid,size=64m `
  kinsun-core-api:local
```

Both containers run as UID/GID `10001:10001`. The API listens on port `8000`;
neither container needs to write application state under `/app`, so ECS can use
a read-only root filesystem. Alembic reads its configuration and version files,
then writes schema changes only through its database connection.

## Staging synthetic consent-policy bootstrap

An empty staging Aurora database has no active consent policy, so consent grant
requests correctly fail closed. After the migration job succeeds, run a separate
one-shot task from the migration image with this command override:

```text
python -m app.consent_policy_bootstrap
```

The task must override these environment values:

```text
APP_ENV=staging
CONSENT_POLICY_VERSION=demo-consent-v1
```

Keep the migration task's existing database secret injection and
`postgresql+psycopg` container entrypoint. Do not add the bootstrap to Alembic or
to API startup. The command rejects every environment except `staging`, creates
only an unsigned synthetic global policy, and leaves
`approved_by_actor_id=NULL`. It serializes writers, is idempotent only when every
controlled field matches exactly, and fails without overwriting when the same
consent-policy version has different or ambiguous rows.

The command writes one JSON receipt to stdout for the retained migration log
group. Its fixed governance fields are `synthetic_only=true`,
`governance_status=UNSIGNED_SYNTHETIC_STAGING_OVERRIDE`, and
`production_approved=false`; it never logs the database URL or credentials.

This policy row alone is not enough for a grant/revoke smoke test. That test
still needs synthetic-only tenant, actor, elder, active tenant membership, and
an authorized care relationship/assignment with `consent:write`,
`consent:read`, and `consent:revoke` scopes. It also needs a server-side test
auth mapping for that synthetic actor. No bootstrap output represents human or
production approval.

## Health contract

- `GET /health`: process liveness only; it does not access Aurora. The image's
  Docker health check uses this endpoint.
- `GET /ready`: traffic readiness; it checks database connectivity and returns
  `503` while Aurora is unavailable. ECS/ALB should use this endpoint when
  deciding whether a task can receive traffic.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

## Local verification

```powershell
uv sync --extra test --extra dev
uv run pytest tests/unit
uv run ruff check .
uv run ruff format --check .
```
