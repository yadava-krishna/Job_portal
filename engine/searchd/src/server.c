/* Unix-socket server. Frame = 4-byte big-endian length + JSON. One thread per connection (at most SPS_MAX_CONN);
 * searches hold the index read lock, so they never wait for each other, only briefly for an update batch. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include <yyjson.h>
#include "proto.h"
#include "server.h"

#define SPS_MAX_CONN 64
static atomic_int g_conns = 0;

static double mono(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + t.tv_nsec / 1e9; }

static bool read_full(int fd, void *b, size_t n) {
    size_t got = 0;
    while (got < n) {
        ssize_t r = read(fd, (char *)b + got, n - got);
        if (r <= 0) { if (r < 0 && errno == EINTR) continue; return false; }
        got += (size_t)r;
    }
    return true;
}

static bool write_full(int fd, const void *b, size_t n) {
    size_t put = 0;
    while (put < n) {
        ssize_t w = send(fd, (const char *)b + put, n - put, MSG_NOSIGNAL);
        if (w <= 0) { if (w < 0 && errno == EINTR) continue; return false; }
        put += (size_t)w;
    }
    return true;
}

static bool send_frame(int fd, const char *json, size_t len) {
    uint32_t be = htonl((uint32_t)len);
    return write_full(fd, &be, 4) && write_full(fd, json, len);
}

static char *respond(sps_state *st, const char *req, size_t len, size_t *out_len) {
    yyjson_mut_doc *d = yyjson_mut_doc_new(NULL);
    yyjson_mut_val *o = yyjson_mut_obj(d);
    yyjson_mut_doc_set_root(d, o);
    yyjson_doc *rd = NULL;
    sps_query q;
    char err[160] = "";
    int kind = sps_parse_request(req, len, &rd, &q, err, sizeof err);
    double t0 = mono();
    pthread_rwlock_rdlock(&st->lock);
    sps_index *ix = st->ix;
    if (kind == REQ_BAD) {
        yyjson_mut_obj_add_bool(d, o, "ok", false);
        yyjson_mut_obj_add_strcpy(d, o, "error", err);
    } else if (!ix) {
        yyjson_mut_obj_add_bool(d, o, "ok", false);
        yyjson_mut_obj_add_str(d, o, "error", "index not ready");
        yyjson_mut_obj_add_bool(d, o, "ready", false);
    } else if (kind == REQ_HEALTH || kind == REQ_STATS) {
        yyjson_mut_obj_add_bool(d, o, "ok", true);
        yyjson_mut_obj_add_bool(d, o, "ready", true);
        yyjson_mut_obj_add_str(d, o, "version", SPS_VERSION);
        yyjson_mut_obj_add_uint(d, o, "docs", ix->nlive);
        yyjson_mut_obj_add_uint(d, o, "generation", ix->generation);
        yyjson_mut_obj_add_real(d, o, "last_sync_age_s", st->last_sync ? mono() - st->last_sync : -1);
        if (kind == REQ_STATS) {
            yyjson_mut_obj_add_uint(d, o, "local_docs", ix->ndocs);
            yyjson_mut_obj_add_real(d, o, "dead_ratio", sps_index_dead_ratio(ix));
            yyjson_mut_obj_add_uint(d, o, "terms", ix->nterms);
            yyjson_mut_obj_add_uint(d, o, "filter_keys", ix->nf);
            yyjson_mut_obj_add_uint(d, o, "rebuilds", st->rebuilds);
            yyjson_mut_obj_add_uint(d, o, "outbox_high_water", (uint64_t)atomic_load(&st->high_water));
        }
    } else if (kind == REQ_SUGGEST) {
        char words[20][SPS_MAX_TOKEN + 1];
        size_t cnt = sps_suggest(ix, q.terms[0], words, q.limit);
        yyjson_mut_obj_add_bool(d, o, "ok", true);
        yyjson_mut_val *arr = yyjson_mut_arr(d);
        for (size_t i = 0; i < cnt; i++) yyjson_mut_arr_add_strcpy(d, arr, words[i]);
        yyjson_mut_obj_add_val(d, o, "suggestions", arr);
    } else {
        sps_result r;
        int32_t today = (int32_t)(time(NULL) / 86400);
        if (sps_search(ix, &q, today, &r)) {
            yyjson_mut_obj_add_bool(d, o, "ok", true);
            yyjson_mut_val *hits = yyjson_mut_arr(d);
            for (uint32_t i = 0; i < r.n; i++) {
                yyjson_mut_val *h = yyjson_mut_arr(d);
                yyjson_mut_arr_add_sint(d, h, r.hits[i].id);
                yyjson_mut_arr_add_real(d, h, r.hits[i].score);
                yyjson_mut_arr_append(hits, h);
            }
            yyjson_mut_obj_add_val(d, o, "hits", hits);
            yyjson_mut_obj_add_uint(d, o, "candidates", r.candidates);
            yyjson_mut_obj_add_uint(d, o, "generation", ix->generation);
            yyjson_mut_obj_add_uint(d, o, "docs", ix->nlive);
            sps_result_free(&r);
        } else {
            yyjson_mut_obj_add_bool(d, o, "ok", false);
            yyjson_mut_obj_add_str(d, o, "error", "out of memory");
        }
    }
    pthread_rwlock_unlock(&st->lock);
    yyjson_mut_obj_add_uint(d, o, "took_us", (uint64_t)((mono() - t0) * 1e6));
    char *json = yyjson_mut_write(d, 0, out_len);
    yyjson_mut_doc_free(d);
    yyjson_doc_free(rd);
    return json;
}

typedef struct { sps_state *st; int fd; } conn_arg;

static void *serve_conn(void *p) {
    conn_arg *a = p;
    char *buf = malloc(SPS_MAX_FRAME);
    struct timeval tv = {.tv_sec = 60}, wtv = {.tv_sec = 10};
    setsockopt(a->fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    setsockopt(a->fd, SOL_SOCKET, SO_SNDTIMEO, &wtv, sizeof wtv);
    while (buf) {
        uint32_t be;
        if (!read_full(a->fd, &be, 4)) break;
        uint32_t len = ntohl(be);
        if (len == 0 || len > SPS_MAX_FRAME) break;  /* protocol violation: close */
        if (!read_full(a->fd, buf, len)) break;
        size_t out_len = 0;
        char *json = respond(a->st, buf, len, &out_len);
        bool ok = json && send_frame(a->fd, json, out_len);
        free(json);
        if (!ok) break;
    }
    free(buf);
    close(a->fd);
    free(a);
    atomic_fetch_sub(&g_conns, 1);
    return NULL;
}

int sps_serve(sps_state *st, const char *path, volatile int *stop) {
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    if (strlen(path) >= sizeof addr.sun_path) return -1;
    strcpy(addr.sun_path, path);
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return -1;
    unlink(path);
    if (bind(fd, (struct sockaddr *)&addr, sizeof addr) < 0 || listen(fd, 128) < 0) {
        fprintf(stderr, "level=error msg=\"cannot listen on the socket\" socket=%s err=\"%s\"\n", path, strerror(errno));
        close(fd);
        return -1;
    }
    chmod(path, 0666);  /* the socket lives in a volume shared only with the backend container */
    struct timeval atv = {.tv_sec = 1};  /* accept() wakes every second to notice SIGTERM */
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &atv, sizeof atv);
    fprintf(stderr, "level=info msg=listening socket=%s\n", path);
    while (!*stop) {
        int c = accept4(fd, NULL, NULL, SOCK_CLOEXEC);
        if (c < 0) { if (errno != EINTR && errno != EAGAIN && errno != EWOULDBLOCK) usleep(10000); continue; }
        if (atomic_fetch_add(&g_conns, 1) >= SPS_MAX_CONN) { atomic_fetch_sub(&g_conns, 1); close(c); continue; }
        conn_arg *a = malloc(sizeof *a);
        pthread_t t;
        if (!a) { close(c); atomic_fetch_sub(&g_conns, 1); continue; }
        a->st = st;
        a->fd = c;
        if (pthread_create(&t, NULL, serve_conn, a) != 0) { close(c); free(a); atomic_fetch_sub(&g_conns, 1); continue; }
        pthread_detach(t);
    }
    close(fd);
    unlink(path);
    return 0;
}
