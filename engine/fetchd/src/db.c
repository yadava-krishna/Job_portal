/* PostgreSQL side of jp-fetchd. PostgreSQL is the contract (blueprint section 4): this process claims due boards with
 * a lease, and writes one crawl_results row (+ its items, by COPY) per board in a single transaction. The Python
 * service applies results and owns every other table; a crash anywhere leaves either nothing or a complete result. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fetchd.h"

PGconn *jpf_db_connect(const char *url, char *err, size_t n) {
    PGconn *c = PQconnectdb(url);
    if (PQstatus(c) != CONNECTION_OK) {
        snprintf(err, n, "%s", PQerrorMessage(c));
        PQfinish(c);
        return NULL;
    }
    PQclear(PQexec(c, "SET application_name = 'jp-fetchd'"));
    PQclear(PQexec(c, "SET statement_timeout = '60s'"));
    return c;
}

static const char *CLAIM =
    "WITH due AS ("
    "  SELECT cs.id FROM crawl_state cs JOIN companies c ON c.id = cs.company_id"
    "  WHERE cs.kind = 'board' AND cs.enabled AND c.enabled AND cs.next_due_at <= now()"
    "    AND (cs.cooldown_until IS NULL OR cs.cooldown_until <= now())"
    "    AND c.ats IN ('greenhouse','lever','ashby','smartrecruiters','recruitee')"
    "    AND NOT EXISTS (SELECT 1 FROM crawl_results r WHERE r.state_id = cs.id AND r.state = 'pending')"
    "  ORDER BY cs.priority DESC, cs.next_due_at LIMIT $1::int FOR UPDATE OF cs SKIP LOCKED)"
    " UPDATE crawl_state s SET next_due_at = now() + make_interval(secs => $2::int)"  /* the lease */
    " FROM due, companies c WHERE s.id = due.id AND c.id = s.company_id"
    " RETURNING s.id, s.target_key, c.ats, c.board_token, coalesce(c.region, ''), coalesce(s.etag, ''),"
    "   coalesce(s.body_hash, ''), (s.last_success_at IS NOT NULL)";

long jpf_db_claim(PGconn *c, const jpf_config *cfg, jpf_job **out, char *err, size_t n) {
    char lim[16], lease[16];
    snprintf(lim, sizeof lim, "%u", cfg->max_claim);
    snprintf(lease, sizeof lease, "%u", cfg->lease_s);
    const char *params[2] = {lim, lease};
    PGresult *r = PQexecParams(c, CLAIM, 2, NULL, params, NULL, NULL, 0);
    if (PQresultStatus(r) != PGRES_TUPLES_OK) {
        snprintf(err, n, "claim: %s", PQerrorMessage(c));
        PQclear(r);
        return -1;
    }
    int rows = PQntuples(r);
    jpf_job *jobs = rows ? calloc((size_t)rows, sizeof *jobs) : NULL;
    if (rows && !jobs) { PQclear(r); snprintf(err, n, "out of memory"); return -1; }
    for (int i = 0; i < rows; i++) {
        jpf_job *j = &jobs[i];
        j->state_id = atoi(PQgetvalue(r, i, 0));
        snprintf(j->target_key, sizeof j->target_key, "%s", PQgetvalue(r, i, 1));
        j->ats = jpf_ats_from(PQgetvalue(r, i, 2));
        snprintf(j->token, sizeof j->token, "%s", PQgetvalue(r, i, 3));
        snprintf(j->region, sizeof j->region, "%s", PQgetvalue(r, i, 4));
        bool has_snapshot = PQgetvalue(r, i, 7)[0] == 't';
        if (has_snapshot) {  /* without a stored snapshot a 304 would leave nothing to serve */
            snprintf(j->etag, sizeof j->etag, "%s", PQgetvalue(r, i, 5));
            snprintf(j->prev_body_hash, sizeof j->prev_body_hash, "%s", PQgetvalue(r, i, 6));
        }
    }
    PQclear(r);
    *out = jobs;
    return rows;
}

static bool exec_ok(PGconn *c, const char *sql, char *err, size_t n) {
    PGresult *r = PQexec(c, sql);
    bool ok = PQresultStatus(r) == PGRES_COMMAND_OK;
    if (!ok) snprintf(err, n, "%s", PQerrorMessage(c));
    PQclear(r);
    return ok;
}

static bool hexval(char ch, uint8_t *v) {
    if (ch >= '0' && ch <= '9') { *v = (uint8_t)(ch - '0'); return true; }
    if (ch >= 'a' && ch <= 'f') { *v = (uint8_t)(ch - 'a' + 10); return true; }
    return false;
}

/* Previous posting hashes of this board, as the Python applier last recorded them. */
static bool load_prev(PGconn *c, const char *target, jpf_map *m, char *err, size_t n) {
    const char *params[1] = {target};
    PGresult *r = PQexecParams(c, "SELECT raw_id, raw_hash FROM crawl_raw_items WHERE target_key = $1", 1, NULL, params, NULL, NULL, 0);
    if (PQresultStatus(r) != PGRES_TUPLES_OK) {
        snprintf(err, n, "load hashes: %s", PQerrorMessage(c));
        PQclear(r);
        return false;
    }
    jpf_map_init(m, (size_t)PQntuples(r));
    for (int i = 0; i < PQntuples(r); i++) {
        const char *h = PQgetvalue(r, i, 1);
        uint8_t v[16], hi, lo;
        bool ok = strlen(h) == 32;
        for (int k = 0; ok && k < 16; k++) ok = hexval(h[2 * k], &hi) && hexval(h[2 * k + 1], &lo) && ((v[k] = (uint8_t)(hi << 4 | lo)), 1);
        if (ok) jpf_map_put(m, PQgetvalue(r, i, 0), v);
    }
    PQclear(r);
    return true;
}

/* COPY text format: backslash, tab, newline and carriage return must be escaped. */
static bool copy_escaped(PGconn *c, const char *s, size_t len) {
    char buf[8192];
    size_t k = 0;
    for (size_t i = 0; i < len; i++) {
        const char *rep = NULL;
        switch (s[i]) { case '\\': rep = "\\\\"; break; case '\t': rep = "\\t"; break; case '\n': rep = "\\n"; break; case '\r': rep = "\\r"; break; }
        if (k + 2 >= sizeof buf) { if (PQputCopyData(c, buf, (int)k) != 1) return false; k = 0; }
        if (rep) { buf[k++] = rep[0]; buf[k++] = rep[1]; }
        else buf[k++] = s[i];
    }
    return k == 0 || PQputCopyData(c, buf, (int)k) == 1;
}

static const char *status_name(jpf_status s) {
    static const char *names[] = {"ok", "not_modified", "unchanged", "not_found", "error", "skipped"};
    return names[s];
}

bool jpf_db_write(PGconn *c, jpf_job *j, char *err, size_t n) {
    if (j->status == ST_SKIPPED) {  /* never fetched: release the lease so it is picked first next tick */
        char id[16];
        snprintf(id, sizeof id, "%d", j->state_id);
        const char *p[1] = {id};
        PQclear(PQexecParams(c, "UPDATE crawl_state SET next_due_at = now() WHERE id = $1::int", 1, NULL, p, NULL, NULL, 0));
        return true;
    }
    char body_hash[33] = "";
    if (j->status == ST_OK) {
        jpf_job_body_hash(j, body_hash);
        if (j->prev_body_hash[0] && !strcmp(body_hash, j->prev_body_hash)) j->status = ST_UNCHANGED;  /* byte-identical */
    }
    jpf_map prev = {0};
    if (j->status == ST_OK && !load_prev(c, j->target_key, &prev, err, n)) return false;
    if (!exec_ok(c, "BEGIN", err, n)) { jpf_map_free(&prev); return false; }
    char sid[16], http[16], dur[24], bytes[24], reqs[16], items[16];
    snprintf(sid, sizeof sid, "%d", j->state_id);
    snprintf(http, sizeof http, "%ld", j->http_status);
    snprintf(dur, sizeof dur, "%ld", j->duration_ms);
    snprintf(bytes, sizeof bytes, "%zu", j->bytes);
    snprintf(reqs, sizeof reqs, "%u", j->requests);
    snprintf(items, sizeof items, "%zu", j->status == ST_OK ? j->board.len : (size_t)0);
    const char *etag = j->etag_out[0] ? j->etag_out : (j->status == ST_NOT_MODIFIED ? j->etag : NULL);
    const char *params[11] = {sid, j->target_key, status_name(j->status), http, etag, body_hash[0] ? body_hash : NULL,
                              j->error[0] ? j->error : NULL, dur, bytes, reqs, items};
    PGresult *r = PQexecParams(c,
        "INSERT INTO crawl_results (state_id, target_key, status, http_status, etag, body_hash, error, duration_ms, bytes, requests,"
        " item_count, state, attempts, created_at) VALUES ($1::int, $2, $3, $4::int, $5, $6, $7, $8::int, $9::bigint, $10::int,"
        " $11::int, 'pending', 0, now()) RETURNING id", 11, NULL, params, NULL, NULL, 0);
    if (PQresultStatus(r) != PGRES_TUPLES_OK) {
        snprintf(err, n, "insert result: %s", PQerrorMessage(c));
        PQclear(r);
        PQclear(PQexec(c, "ROLLBACK"));
        jpf_map_free(&prev);
        return false;
    }
    char rid[32];
    snprintf(rid, sizeof rid, "%s", PQgetvalue(r, 0, 0));
    PQclear(r);
    size_t changed = 0;
    if (j->status == ST_OK && j->board.len) {
        r = PQexec(c, "COPY crawl_result_items (result_id, raw_id, raw_hash, raw) FROM STDIN");
        bool ok = PQresultStatus(r) == PGRES_COPY_IN;
        PQclear(r);
        for (size_t i = 0; ok && i < j->board.len; i++) {
            jpf_posting *p = &j->board.items[i];
            const uint8_t *old = jpf_map_get(&prev, p->id);
            bool same = old && !memcmp(old, p->hash, 16);
            char hex[33], head[96];
            jpf_hex(p->hash, 16, hex);
            snprintf(head, sizeof head, "%s\t", rid);
            ok = PQputCopyData(c, head, (int)strlen(head)) == 1 && copy_escaped(c, p->id, strlen(p->id)) &&
                 PQputCopyData(c, "\t", 1) == 1 && PQputCopyData(c, hex, 32) == 1 && PQputCopyData(c, "\t", 1) == 1;
            if (ok && same) ok = PQputCopyData(c, "\\N\n", 3) == 1;  /* unchanged: id and hash only */
            else if (ok) { ok = copy_escaped(c, p->json, p->json_len) && PQputCopyData(c, "\n", 1) == 1; changed++; }
        }
        if (PQputCopyEnd(c, ok ? NULL : "aborted") != 1) ok = false;
        r = PQgetResult(c);
        if (PQresultStatus(r) != PGRES_COMMAND_OK) ok = false;
        if (!ok) snprintf(err, n, "copy items: %s", PQerrorMessage(c));
        PQclear(r);
        while ((r = PQgetResult(c))) PQclear(r);
        if (!ok) { PQclear(PQexec(c, "ROLLBACK")); jpf_map_free(&prev); return false; }
    }
    jpf_map_free(&prev);
    bool ok = exec_ok(c, "COMMIT", err, n);
    if (ok) PQclear(PQexec(c, "NOTIFY jpse_crawl_results"));  /* a wake-up only; the table is the delivery */
    fprintf(stderr, "level=info msg=board target=%s status=%s http=%ld ms=%ld bytes=%zu postings=%zu changed=%zu\n", j->target_key,
            status_name(j->status), j->http_status, j->duration_ms, j->bytes, j->status == ST_OK ? j->board.len : (size_t)0, changed);
    return ok;
}
