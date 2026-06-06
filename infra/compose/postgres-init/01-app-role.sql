-- Phase 3 (RLS FORCE): a NON-SUPERUSER application role.
--
-- The app connects as `pdlc_app` so row-level security actually applies to it
-- (superusers — incl. the default `postgres` — always bypass RLS). Migrations
-- run as the owner (`postgres`); ALTER DEFAULT PRIVILEGES below makes every
-- table the owner later creates auto-grant DML to pdlc_app.
--
-- Runs once, at first DB init (fresh `pgdata` volume), as the superuser.
-- The dev password is a placeholder — change it (and PDLC_DB_URL) for real use.

CREATE ROLE pdlc_app LOGIN PASSWORD 'pdlc_app' NOSUPERUSER NOCREATEDB NOCREATEROLE;

GRANT CONNECT ON DATABASE pdlc TO pdlc_app;
GRANT USAGE ON SCHEMA public TO pdlc_app;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pdlc_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO pdlc_app;
