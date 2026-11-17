/* jp-fetchd main loop: claim due boards, fetch them all concurrently, write each result as it completes, sleep, repeat.
 * Configuration comes from the environment (no secrets in arguments). SIGTERM/SIGINT finish the current tick cleanly. */
#define _GNU_SOURCE
#include <curl/curl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "fetchd.h"

static volatile int g_stop = 0;
static void on_signal(int s) { (void)s; g_stop = 1; }

static unsigned env_u(const char *k, unsigned d, unsigned lo, unsigned hi) {
    const char *v = getenv(k);
    if (!v || !*v) return d;
    unsigned long x = strtoul(v, NULL, 10);
    return x < lo ? lo : x > hi ? hi : (unsigned)x;
}

typedef struct { PGconn *db; unsigned written, failed; } tick_ctx;

static void on_done(jpf_job *j, void *ud) {
    tick_ctx *t = ud;
    char err[512] = "";
    if (jpf_db_write(t->db, j, err, sizeof err)) t->written++;
    else { t->failed++; fprintf(stderr, "level=error msg=\"write failed\" target=%s err=\"%s\"\n", j->target_key, err); }
    /* free the board's memory now; the result is in the database */
    free(j->body); j->body = NULL; j->body_cap = j->body_len = 0;
    jpf_board_free(&j->board);
}

static int tick(const jpf_config *cfg) {
    char err[512] = "";
    PGconn *db = jpf_db_connect(cfg->database_url, err, sizeof err);
    if (!db) { fprintf(stderr, "level=error msg=\"database unavailable\" err=\"%s\"\n", strtok(err, "\n")); return -1; }
    jpf_job *jobs = NULL;
    long n = jpf_db_claim(db, cfg, &jobs, err, sizeof err);
    if (n < 0) { fprintf(stderr, "level=error msg=\"%s\"\n", err); PQfinish(db); return -1; }
    if (n > 0) {
        for (long i = 0; i < n; i++) jpf_job_prepare(&jobs[i]);
        jpf_fetcher f;
        jpf_fetcher_init(&f, cfg);
        tick_ctx t = {.db = db};
        jpf_fetch_all(&f, jobs, (size_t)n, cfg->budget_s, on_done, &t, &g_stop);
        jpf_fetcher_free(&f);
        fprintf(stderr, "level=info msg=tick claimed=%ld written=%u failed=%u\n", n, t.written, t.failed);
        for (long i = 0; i < n; i++) jpf_job_free(&jobs[i]);
    }
    free(jobs);
    PQfinish(db);
    return (int)n;
}

int main(void) {
    jpf_config cfg = {0};
    const char *url = getenv("JPF_DATABASE_URL");
    if (!url || !*url) { fprintf(stderr, "level=error msg=\"JPF_DATABASE_URL is not set\"\n"); return 2; }
    snprintf(cfg.database_url, sizeof cfg.database_url, "%s", url);
    const char *origin = getenv("JPF_TEST_ORIGIN");
    if (origin && *origin) {
        if (strncmp(origin, "http://127.0.0.1:", 17) != 0) { fprintf(stderr, "level=error msg=\"JPF_TEST_ORIGIN must be http://127.0.0.1:PORT\"\n"); return 2; }
        snprintf(cfg.test_origin, sizeof cfg.test_origin, "%s", origin);
        fprintf(stderr, "level=warn msg=\"TEST MODE: requests go to %s\"\n", origin);
    }
    cfg.global = env_u("JPF_GLOBAL", 16, 1, 32);
    cfg.per_host = env_u("JPF_PER_HOST", 2, 1, 4);
    cfg.timeout_s = env_u("JPF_TIMEOUT_S", 60, 5, 180);
    cfg.max_claim = env_u("JPF_MAX_CLAIM", 300, 1, 2000);
    cfg.lease_s = env_u("JPF_LEASE_S", 900, 60, 7200);
    cfg.tick_s = env_u("JPF_TICK_S", 30, 1, 3600);
    cfg.budget_s = env_u("JPF_BUDGET_S", 300, 5, 1800);
    cfg.once = getenv("JPF_ONCE") && !strcmp(getenv("JPF_ONCE"), "1");
    signal(SIGTERM, on_signal);
    signal(SIGINT, on_signal);
    signal(SIGPIPE, SIG_IGN);
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 2;
    fprintf(stderr, "level=info msg=start version=%s global=%u per_host=%u\n", JPF_VERSION, cfg.global, cfg.per_host);
    do {
        tick(&cfg);
        for (unsigned s = 0; !cfg.once && !g_stop && s < cfg.tick_s; s++) sleep(1);
    } while (!cfg.once && !g_stop);
    curl_global_cleanup();
    fprintf(stderr, "level=info msg=stop\n");
    return 0;
}
