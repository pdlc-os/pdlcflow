#!/bin/bash
# Phase 3 (RLS FORCE): create the NON-SUPERUSER application role at first DB init.
# The app connects as pdlc_app so row-level security applies (superusers bypass
# it). Password comes from PDLC_APP_DB_PASSWORD (default 'pdlc_app' for dev) so it
# can match PDLC_DB_URL without editing this file. Migrations run as the owner;
# ALTER DEFAULT PRIVILEGES makes owner-created tables auto-grant DML to pdlc_app.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
  create role pdlc_app login password '${PDLC_APP_DB_PASSWORD:-pdlc_app}' nosuperuser nocreatedb nocreaterole;
  grant connect on database "$POSTGRES_DB" to pdlc_app;
  grant usage on schema public to pdlc_app;
  -- CREATE so the LangGraph PostgresSaver can create + own (and RLS-FORCE) its
  -- checkpoint tables when the app connects as pdlc_app.
  grant create on schema public to pdlc_app;
  alter default privileges for role "$POSTGRES_USER" in schema public
    grant select, insert, update, delete on tables to pdlc_app;
  alter default privileges for role "$POSTGRES_USER" in schema public
    grant usage, select on sequences to pdlc_app;
SQL
