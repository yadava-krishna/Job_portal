#!/usr/bin/env bash
# Least-privilege database accounts for the two C services (JPSE blueprint §11). Safe to run again.
#
#   jpse_fetchd  : reads its queue (crawl_state, companies, crawl_raw_items, crawl_results), stamps claims
#                  (crawl_state.next_due_at / last_attempt_at), inserts results. Nothing else.
#   jpse_searchd : reads catalogue_postings and index_outbox. Nothing else.
#
# Passwords are random, written to .env (JPSE_FETCHD_DB_PASSWORD, JPSE_SEARCHD_DB_PASSWORD) if missing, and never
# printed. The SQL goes to psql on stdin, so the passwords never appear in a process list.
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
touch .env
for v in JPSE_FETCHD_DB_PASSWORD JPSE_SEARCHD_DB_PASSWORD; do
  grep -q "^${v}=" .env || echo "${v}=$(openssl rand -hex 24)" >> .env
done
set -a; . ./.env; set +a
docker compose -p jobpilot exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'jpse_fetchd') THEN CREATE ROLE jpse_fetchd LOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'jpse_searchd') THEN CREATE ROLE jpse_searchd LOGIN; END IF;
END \$\$;
ALTER ROLE jpse_fetchd WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '${JPSE_FETCHD_DB_PASSWORD}';
ALTER ROLE jpse_searchd WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '${JPSE_SEARCHD_DB_PASSWORD}';
GRANT CONNECT ON DATABASE jobpilot TO jpse_fetchd, jpse_searchd;
GRANT USAGE ON SCHEMA public TO jpse_fetchd, jpse_searchd;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM jpse_fetchd, jpse_searchd;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM jpse_fetchd, jpse_searchd;
GRANT SELECT ON crawl_state, companies, crawl_raw_items, crawl_results TO jpse_fetchd;
GRANT UPDATE (next_due_at, last_attempt_at) ON crawl_state TO jpse_fetchd;
GRANT INSERT ON crawl_results, crawl_result_items TO jpse_fetchd;
GRANT USAGE ON SEQUENCE crawl_results_id_seq, crawl_result_items_id_seq TO jpse_fetchd;
GRANT SELECT ON catalogue_postings, index_outbox TO jpse_searchd;
SQL
echo "jpse_fetchd and jpse_searchd are set up (passwords in .env)."
