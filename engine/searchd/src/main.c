/* jp-searchd: load the index, keep it in sync in a background thread, serve searches on a Unix socket. */
#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "sync.h"

static volatile int g_stop = 0;
static void on_signal(int s) { (void)s; g_stop = 1; }

typedef struct { sps_state *st; char url[1024]; unsigned refresh_s, rebuild_s; } sync_cfg;

static unsigned env_u(const char *k, unsigned d, unsigned lo, unsigned hi) {
    const char *v = getenv(k);
    if (!v || !*v) return d;
    unsigned long x = strtoul(v, NULL, 10);
    return x < lo ? lo : x > hi ? hi : (unsigned)x;
}

static PGconn *connect_db(const char *url) {
    PGconn *c = PQconnectdb(url);
    if (PQstatus(c) != CONNECTION_OK) {
        fprintf(stderr, "level=error msg=\"database unavailable\" err=\"%s\"\n", strtok(PQerrorMessage(c), "\n"));
        PQfinish(c);
        return NULL;
    }
    PQclear(PQexec(c, "SET application_name = 'jp-searchd'"));
    PQclear(PQexec(c, "SET statement_timeout = '120s'"));
    return c;
}

static void *sync_loop(void *p) {
    sync_cfg *cfg = p;
    sps_idmap seen;
    sps_idmap_init(&seen, 4096);
    double avg[SPS_NFIELDS] = {0};
    bool have_avg = false;
    time_t last_rebuild = 0;
    PGconn *c = NULL;
    while (!g_stop) {
        if (!c && !(c = connect_db(cfg->url))) { sleep(5); continue; }
        char err[512] = "";
        bool need = !cfg->st->ix || time(NULL) - last_rebuild >= (time_t)cfg->rebuild_s;
        if (!need) {
            pthread_rwlock_rdlock(&cfg->st->lock);
            need = sps_index_dead_ratio(cfg->st->ix) > 0.3;
            pthread_rwlock_unlock(&cfg->st->lock);
        }
        if (need) {
            if (!sps_rebuild(c, cfg->st, &seen, have_avg ? avg : NULL, err, sizeof err)) goto fail;
            last_rebuild = time(NULL);
            double m[SPS_NFIELDS];
            pthread_rwlock_rdlock(&cfg->st->lock);
            sps_index_measured_avg(cfg->st->ix, m);
            pthread_rwlock_unlock(&cfg->st->lock);
            bool drift = false;  /* impacts depend on average field lengths: rebuild once with the measured ones */
            for (int f = 0; f < SPS_NFIELDS; f++) drift |= !have_avg ? fabs(m[f] - cfg->st->ix->avg_len[f]) > 0.2 * cfg->st->ix->avg_len[f] : false;
            memcpy(avg, m, sizeof avg);
            have_avg = true;
            if (drift) last_rebuild = 0;
            continue;
        }
        if (sps_refresh(c, cfg->st, &seen, err, sizeof err) < 0) goto fail;
        for (unsigned s = 0; s < cfg->refresh_s && !g_stop; s++) sleep(1);
        continue;
    fail:
        fprintf(stderr, "level=error msg=\"sync failed\" err=\"%s\"\n", strtok(err, "\n") ? err : "");
        PQfinish(c);
        c = NULL;
        sleep(5);
    }
    if (c) PQfinish(c);
    sps_idmap_free(&seen);
    return NULL;
}

int main(void) {
    const char *url = getenv("JPS_DATABASE_URL");
    if (!url || !*url) { fprintf(stderr, "level=error msg=\"JPS_DATABASE_URL is not set\"\n"); return 2; }
    const char *sock = getenv("JPS_SOCKET");
    if (!sock || !*sock) sock = "/run/jpse/searchd.sock";
    static sps_state st;
    pthread_rwlock_init(&st.lock, NULL);
    static sync_cfg cfg;
    cfg.st = &st;
    snprintf(cfg.url, sizeof cfg.url, "%s", url);
    cfg.refresh_s = env_u("JPS_REFRESH_S", 2, 1, 300);
    cfg.rebuild_s = env_u("JPS_REBUILD_S", 6 * 3600, 60, 7 * 86400);
    struct sigaction sa = {.sa_handler = on_signal};
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT, &sa, NULL);
    signal(SIGPIPE, SIG_IGN);
    fprintf(stderr, "level=info msg=start version=%s\n", SPS_VERSION);
    pthread_t t;
    if (pthread_create(&t, NULL, sync_loop, &cfg) != 0) return 2;
    int rc = sps_serve(&st, sock, &g_stop);  /* answers "not ready" until the first build is in */
    g_stop = 1;
    pthread_join(t, NULL);
    pthread_rwlock_wrlock(&st.lock);
    sps_index_free(st.ix);
    st.ix = NULL;
    pthread_rwlock_unlock(&st.lock);
    fprintf(stderr, "level=info msg=stop\n");
    return rc ? 1 : 0;
}
