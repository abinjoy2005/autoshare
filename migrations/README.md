# Database migration

The FastAPI application intentionally does not create or alter tables during startup.
Apply `001_initial_schema.sql` once to the Supabase project before deploying the API.
It can be run from the Supabase SQL editor or with `psql` against the project's
IPv4 transaction-pooler connection on port `6543`.

Configure the deployment's `DATABASE_URL` with the Supabase transaction-pooler DSN,
including `sslmode=require`. The SQLAlchemy database module selects `pg8000`, enables
TLS, and uses a small connection pool suitable for serverless instances.

Set `JWT_SECRET_KEY` and `ADMIN_API_KEY` to distinct random secrets of at least 32
characters. Keep `GEMINI_API_KEY` in Vercel environment variables. Do not commit a
real `.env` file. Set `COOKIE_SECURE=true` on HTTPS deployments and
`COOKIE_SECURE=false` for local HTTP development. If it is unset, the API uses
the incoming request scheme.

Driver review is an administrative operation: submit the driver and vehicle IDs to
`POST /api/admin/drivers/{driver_id}/vehicles/{vehicle_id}/verify?verified=true`
with the `X-Admin-API-Key` header. The driver can go online only after that review.
