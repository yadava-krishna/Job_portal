#ifndef FETCHD_H
#define FETCHD_H
#include <curl/curl.h>
#include <xxhash.h>
#include "jpf.h"

typedef struct {
    char database_url[1024];
    char test_origin[256];   /* tests only: send https://HOST/PATH to ORIGIN/HOST/PATH and allow loopback */
    unsigned global, per_host, timeout_s, max_claim, lease_s, tick_s;
    double budget_s;
    bool once;
} jpf_config;

typedef enum { ST_OK, ST_NOT_MODIFIED, ST_UNCHANGED, ST_NOT_FOUND, ST_ERROR, ST_SKIPPED } jpf_status;
typedef enum { JOB_WAITING, JOB_RUNNING, JOB_DONE } jpf_phase;

typedef struct jpf_job {
    /* the target, from crawl_state + companies */
    int state_id;
    char target_key[201];
    jpf_ats ats;
    char token[JPF_MAX_TOKEN_LEN + 1];
    char region[16];
    char etag[301];
    char prev_body_hash[41];
    char host[256];
    /* progress */
    jpf_phase phase;
    jpf_status status;
    bool reported, sent_etag, too_large;
    int attempt;
    unsigned offset;
    double started, not_before;
    long duration_ms, http_status;
    unsigned requests;
    size_t bytes;
    char etag_out[301];
    char redirect_url[JPF_MAX_URL_LEN + 1];   /* set while following a checked redirect by hand */
    unsigned redirects;
    size_t page_bytes;                       /* bytes of the current request, taken back out of `bytes` on a retry */
    char error[300];
    /* transfer */
    CURL *easy;
    struct curl_slist *headers;
    char *body;
    size_t body_len, body_cap;
    XXH3_state_t *body_hash;
    jpf_board board;
} jpf_job;

typedef struct { char host[256]; int inflight; double tokens, updated, rps; } host_slot;
typedef struct { host_slot *v; size_t n, cap; } host_table;

typedef struct jpf_fetcher {
    const jpf_config *cfg;
    CURLM *multi;
    unsigned inflight;
    host_table hosts;
} jpf_fetcher;

/* fetch.c */
void jpf_fetcher_init(jpf_fetcher *f, const jpf_config *cfg);
void jpf_fetcher_free(jpf_fetcher *f);
bool jpf_job_prepare(jpf_job *j);
#define JPF_REFILL_S 10.0
typedef struct { jpf_job **v; size_t n, cap; } jpf_jobs;
bool jpf_jobs_push(jpf_jobs *js, jpf_job *j);
void jpf_fetch_run(jpf_fetcher *f, jpf_jobs *js, double budget_s, void (*on_done)(jpf_job *, void *),
                   size_t (*refill)(jpf_jobs *, void *), void *ud, volatile int *stop);
void jpf_job_free(jpf_job *j);
void jpf_job_body_hash(const jpf_job *j, char out[33]);

/* db.c */
#include <libpq-fe.h>
PGconn *jpf_db_connect(const char *url, char *err, size_t n);
long jpf_db_claim(PGconn *c, const jpf_config *cfg, unsigned limit, jpf_jobs *out, char *err, size_t n);
bool jpf_db_write(PGconn *c, jpf_job *j, char *err, size_t n);
#endif
