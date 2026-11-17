/* Keeping the index equal to PostgreSQL (blueprint section 7).
 *
 * Full build: a server-side cursor over the open postings, 2,000 rows at a time, into a NEW index that is swapped in
 * under the write lock. Incremental: every refresh, index_outbox events with id > high_water - OVERLAP are read, events
 * not seen before name the postings to re-read, and each posting is re-read in its CURRENT state (so applying is
 * idempotent and order does not matter). The overlap catches transactions that committed out of id order; anything
 * older is reconciled by the periodic full rebuild. */
#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <libpq-fe.h>
#include <yyjson.h>
#include "sync.h"

#define OVERLAP 2000
#define COLS "id, revision, title, company, coalesce(location_normalized, location, ''), coalesce(country, ''), " \
    "coalesce(remote_scope::text, ''), coalesce(work_mode, ''), coalesce(employment_type, ''), coalesce(seniority, ''), source, " \
    "coalesce(company_id, 0), coalesce(posted_at - date '1970-01-01', -1), coalesce(salary_currency, ''), salary_min, salary_max, " \
    "coalesce(skills::text, ''), left(coalesce(description, ''), 8000), " \
    "(closed_at IS NULL AND (expires_at IS NULL OR expires_at >= current_date))"

static double mono(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }

static bool row_doc(PGresult *r, int i, sps_doc *d, yyjson_doc **scope_doc) {
    memset(d, 0, sizeof *d);
    d->id = strtoll(PQgetvalue(r, i, 0), NULL, 10);
    d->revision = atoi(PQgetvalue(r, i, 1));
    d->text[F_TITLE] = PQgetvalue(r, i, 2);
    d->text[F_COMPANY] = PQgetvalue(r, i, 3);
    d->text[F_LOCATION] = PQgetvalue(r, i, 4);
    d->country = PQgetvalue(r, i, 5);
    const char *scope = PQgetvalue(r, i, 6);
    *scope_doc = NULL;
    if (scope[0] == '[') {
        *scope_doc = yyjson_read(scope, strlen(scope), 0);
        yyjson_val *arr = *scope_doc ? yyjson_doc_get_root(*scope_doc) : NULL, *v;
        size_t k, max;
        if (yyjson_is_arr(arr))
            yyjson_arr_foreach(arr, k, max, v) if (yyjson_is_str(v) && d->n_remote < 16) d->remote_scope[d->n_remote++] = yyjson_get_str(v);
    }
    d->work_mode = PQgetvalue(r, i, 7);
    d->employment_type = PQgetvalue(r, i, 8);
    d->seniority = PQgetvalue(r, i, 9);
    d->source = PQgetvalue(r, i, 10);
    d->company_id = atoi(PQgetvalue(r, i, 11));
    d->posted_day = atoi(PQgetvalue(r, i, 12));
    d->currency = PQgetvalue(r, i, 13);
    d->sal_min = PQgetisnull(r, i, 14) ? NAN : atof(PQgetvalue(r, i, 14));
    d->sal_max = PQgetisnull(r, i, 15) ? NAN : atof(PQgetvalue(r, i, 15));
    d->text[F_SKILLS] = PQgetvalue(r, i, 16);  /* the JSON list as text tokenizes to its words */
    d->text[F_DESC] = PQgetvalue(r, i, 17);
    return PQgetvalue(r, i, 18)[0] == 't';
}

static bool exec_ok(PGconn *c, const char *sql) {
    PGresult *r = PQexec(c, sql);
    bool ok = PQresultStatus(r) == PGRES_COMMAND_OK;
    PQclear(r);
    return ok;
}

int64_t sps_outbox_max(PGconn *c) {
    PGresult *r = PQexec(c, "SELECT coalesce(max(id), 0) FROM index_outbox");
    int64_t v = PQresultStatus(r) == PGRES_TUPLES_OK ? strtoll(PQgetvalue(r, 0, 0), NULL, 10) : -1;
    PQclear(r);
    return v;
}

sps_index *sps_build(PGconn *c, const double *avg, char *err, size_t n) {
    sps_index *ix = sps_index_new(avg);
    if (!ix) { snprintf(err, n, "out of memory"); return NULL; }
    if (!exec_ok(c, "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY") ||
        !exec_ok(c, "DECLARE ix_cur NO SCROLL CURSOR FOR SELECT " COLS " FROM catalogue_postings"
                    " WHERE closed_at IS NULL AND (expires_at IS NULL OR expires_at >= current_date) ORDER BY id")) {
        snprintf(err, n, "build: %s", PQerrorMessage(c));
        exec_ok(c, "ROLLBACK");
        sps_index_free(ix);
        return NULL;
    }
    for (;;) {
        PGresult *r = PQexec(c, "FETCH 2000 FROM ix_cur");
        if (PQresultStatus(r) != PGRES_TUPLES_OK) { snprintf(err, n, "fetch: %s", PQerrorMessage(c)); PQclear(r); exec_ok(c, "ROLLBACK"); sps_index_free(ix); return NULL; }
        int rows = PQntuples(r);
        for (int i = 0; i < rows; i++) {
            sps_doc d;
            yyjson_doc *sd;
            if (row_doc(r, i, &d, &sd)) sps_index_upsert(ix, &d);
            yyjson_doc_free(sd);
        }
        PQclear(r);
        if (rows == 0) break;
    }
    exec_ok(c, "CLOSE ix_cur");
    exec_ok(c, "COMMIT");
    return ix;
}

/* Applies outbox events after *high_water - OVERLAP that `seen` has not recorded. Returns postings applied or -1. */
long sps_refresh(PGconn *c, sps_state *st, sps_idmap *seen, char *err, size_t n) {
    char from[32];
    snprintf(from, sizeof from, "%lld", (long long)(st->high_water > OVERLAP ? st->high_water - OVERLAP : 0));
    const char *p1[1] = {from};
    PGresult *ev = PQexecParams(c, "SELECT id, posting_id FROM index_outbox WHERE id > $1::bigint ORDER BY id LIMIT 20000", 1, NULL, p1, NULL, NULL, 0);
    if (PQresultStatus(ev) != PGRES_TUPLES_OK) { snprintf(err, n, "outbox: %s", PQerrorMessage(c)); PQclear(ev); return -1; }
    /* posting ids of unseen events, as a Postgres array literal */
    size_t cap = 64, len = 1;
    char *arr = malloc(cap);
    if (!arr) { PQclear(ev); return -1; }
    arr[0] = '{';
    long fresh = 0;
    int64_t hw = st->high_water;
    for (int i = 0; i < PQntuples(ev); i++) {
        int64_t eid = strtoll(PQgetvalue(ev, i, 0), NULL, 10);
        uint32_t dummy;
        if (eid > hw) hw = eid;
        if (sps_idmap_get(seen, eid, &dummy)) continue;
        sps_idmap_put(seen, eid, 1);
        const char *pid = PQgetvalue(ev, i, 1);
        size_t pl = strlen(pid);
        if (len + pl + 3 > cap) { while (len + pl + 3 > cap) cap *= 2; char *a = realloc(arr, cap); if (!a) { free(arr); PQclear(ev); return -1; } arr = a; }
        if (fresh++) arr[len++] = ',';
        memcpy(arr + len, pid, pl);
        len += pl;
    }
    PQclear(ev);
    arr[len++] = '}';
    arr[len] = 0;
    long applied = 0;
    if (fresh) {
        const char *p2[1] = {arr};
        PGresult *r = PQexecParams(c, "SELECT " COLS " FROM catalogue_postings WHERE id = ANY($1::bigint[])", 1, NULL, p2, NULL, NULL, 0);
        if (PQresultStatus(r) != PGRES_TUPLES_OK) { snprintf(err, n, "postings: %s", PQerrorMessage(c)); PQclear(r); free(arr); return -1; }
        pthread_rwlock_wrlock(&st->lock);
        for (int i = 0; i < PQntuples(r); i++) {
            sps_doc d;
            yyjson_doc *sd;
            bool open = row_doc(r, i, &d, &sd);
            if (open) sps_index_upsert(st->ix, &d);
            else sps_index_remove(st->ix, d.id);
            yyjson_doc_free(sd);
            applied++;
        }
        pthread_rwlock_unlock(&st->lock);
        PQclear(r);
    }
    free(arr);
    st->high_water = hw;
    st->last_sync = mono();
    return applied;
}

/* Rebuilds into a new index and swaps it in. Events that arrive during the build are caught by the next refresh,
 * because high_water is taken BEFORE the snapshot and the overlap re-reads around it. */
bool sps_rebuild(PGconn *c, sps_state *st, sps_idmap *seen, const double *avg, char *err, size_t n) {
    int64_t hw = sps_outbox_max(c);
    if (hw < 0) { snprintf(err, n, "outbox max: %s", PQerrorMessage(c)); return false; }
    double t0 = mono();
    sps_index *fresh = sps_build(c, avg, err, n);
    if (!fresh) return false;
    pthread_rwlock_wrlock(&st->lock);
    sps_index *old = st->ix;
    st->ix = fresh;
    st->high_water = hw;
    st->rebuilds++;
    pthread_rwlock_unlock(&st->lock);
    sps_index_free(old);
    sps_idmap_free(seen);
    sps_idmap_init(seen, 4096);  /* forget seen events: the overlap after a rebuild re-applies them idempotently */
    st->last_sync = mono();
    fprintf(stderr, "level=info msg=rebuilt docs=%u terms=%u filter_keys=%u seconds=%.2f high_water=%lld\n", fresh->nlive,
            fresh->nterms, fresh->nf, mono() - t0, (long long)hw);
    return true;
}
