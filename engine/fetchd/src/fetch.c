/* The fetch loop: libcurl multi interface, one event loop, many boards in flight.
 *
 * Politeness (blueprint section 5): at most JPF_GLOBAL transfers overall, JPF_PER_HOST per host, and a token bucket
 * per host (jpf_host_rps). A board is a small state machine: first page (with If-None-Match), further pages for
 * SmartRecruiters, retries after 2 s and 6 s on timeouts / 429 / 5xx (the same as backend/services/ats/base.py), then
 * done. Every connection's peer address is checked (private, loopback, link-local and metadata ranges are refused),
 * redirects stay on HTTPS, at most 5 of them, and the final host must still be a permitted ATS API host. */
#define _GNU_SOURCE
#include <curl/curl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <time.h>
#include <xxhash.h>
#include "fetchd.h"

static double now_s(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

/* ---- per-host state (host_slot / host_table in fetchd.h) ---- */

static host_slot *host_get(host_table *t, const char *host) {
    for (size_t i = 0; i < t->n; i++)
        if (!strcasecmp(t->v[i].host, host)) return &t->v[i];
    if (t->n == t->cap) {
        size_t cap = t->cap ? t->cap * 2 : 16;
        host_slot *v = realloc(t->v, cap * sizeof *v);
        if (!v) return NULL;
        t->v = v;
        t->cap = cap;
    }
    host_slot *h = &t->v[t->n++];
    memset(h, 0, sizeof *h);
    snprintf(h->host, sizeof h->host, "%s", host);
    h->rps = jpf_host_rps(host);
    h->tokens = 1.0;
    h->updated = now_s();
    return h;
}

static bool host_take(host_slot *h, double t) {
    h->tokens = h->tokens + (t - h->updated) * h->rps;
    if (h->tokens > 1.0) h->tokens = 1.0;
    h->updated = t;
    if (h->tokens < 1.0) return false;
    h->tokens -= 1.0;
    return true;
}

/* ---- transfer callbacks ---- */
static size_t on_body(char *p, size_t sz, size_t n, void *ud) {
    jpf_job *j = ud;
    size_t len = sz * n;
    if (j->body_len + len > JPF_MAX_BODY_BYTES || j->bytes + len > JPF_MAX_BOARD_BYTES) {
        j->too_large = true;
        return 0;  /* aborts the transfer with CURLE_WRITE_ERROR */
    }
    if (j->body_len + len + 1 > j->body_cap) {
        size_t cap = j->body_cap ? j->body_cap : 65536;
        while (cap < j->body_len + len + 1) cap *= 2;
        char *b = realloc(j->body, cap);
        if (!b) return 0;
        j->body = b;
        j->body_cap = cap;
    }
    memcpy(j->body + j->body_len, p, len);
    j->body_len += len;
    j->bytes += len;
    return len;
}

static size_t on_header(char *p, size_t sz, size_t n, void *ud) {
    jpf_job *j = ud;
    size_t len = sz * n;
    if (len > 6 && !strncasecmp(p, "etag:", 5)) {
        size_t s = 5;
        while (s < len && (p[s] == ' ' || p[s] == '\t')) s++;
        size_t e = len;
        while (e > s && (p[e - 1] == '\r' || p[e - 1] == '\n' || p[e - 1] == ' ')) e--;
        if (e > s && e - s < sizeof j->etag_out) {
            memcpy(j->etag_out, p + s, e - s);
            j->etag_out[e - s] = 0;
        }
    }
    return len;
}

static curl_socket_t on_open_socket(void *ud, curlsocktype purpose, struct curl_sockaddr *addr) {
    jpf_config *cfg = ud;
    (void)purpose;
    if (jpf_ip_forbidden(&addr->addr, cfg->test_origin[0] != 0)) return CURL_SOCKET_BAD;  /* SSRF guard, every hop */
    return socket(addr->family, addr->socktype, addr->protocol);
}

/* The URL actually requested: in test mode https://HOST/PATH becomes ORIGIN/HOST/PATH (a local fixture server). */
static void effective_url(const jpf_config *cfg, const char *url, char *out, size_t n) {
    if (!cfg->test_origin[0] || strncmp(url, "https://", 8) != 0) { snprintf(out, n, "%s", url); return; }
    snprintf(out, n, "%s/%s", cfg->test_origin, url + 8);
}

static bool url_host(const char *url, char *host, size_t n) {
    CURLU *u = curl_url();
    char *h = NULL;
    bool ok = u && curl_url_set(u, CURLUPART_URL, url, 0) == CURLUE_OK && curl_url_get(u, CURLUPART_HOST, &h, 0) == CURLUE_OK &&
              strlen(h) < n;
    if (ok) snprintf(host, n, "%s", h);
    curl_free(h);
    curl_url_cleanup(u);
    return ok;
}

static bool start(jpf_fetcher *f, jpf_job *j) {
    char url[JPF_MAX_URL_LEN + 1], eff[JPF_MAX_URL_LEN + 300];
    if (!jpf_board_url(j->ats, j->token, j->region, j->offset, url, sizeof url)) return false;
    effective_url(f->cfg, url, eff, sizeof eff);
    CURL *e = curl_easy_init();
    if (!e) return false;
    j->body_len = 0;
    j->http_status = 0;
    curl_easy_setopt(e, CURLOPT_URL, eff);
    curl_easy_setopt(e, CURLOPT_PRIVATE, j);
    curl_easy_setopt(e, CURLOPT_USERAGENT, JPF_USER_AGENT);
    curl_easy_setopt(e, CURLOPT_ACCEPT_ENCODING, "");
    curl_easy_setopt(e, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(e, CURLOPT_MAXREDIRS, 5L);
    const char *protos = f->cfg->test_origin[0] ? "http,https" : "https";
    curl_easy_setopt(e, CURLOPT_PROTOCOLS_STR, protos);
    curl_easy_setopt(e, CURLOPT_REDIR_PROTOCOLS_STR, protos);
    curl_easy_setopt(e, CURLOPT_UNRESTRICTED_AUTH, 0L);
    curl_easy_setopt(e, CURLOPT_NOPROXY, "*");  /* never route through an inherited proxy setting */
    curl_easy_setopt(e, CURLOPT_CONNECTTIMEOUT, 8L);
    curl_easy_setopt(e, CURLOPT_TIMEOUT, (long)f->cfg->timeout_s);
    curl_easy_setopt(e, CURLOPT_LOW_SPEED_LIMIT, 1024L);
    curl_easy_setopt(e, CURLOPT_LOW_SPEED_TIME, 25L);
    curl_easy_setopt(e, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(e, CURLOPT_WRITEFUNCTION, on_body);
    curl_easy_setopt(e, CURLOPT_WRITEDATA, j);
    curl_easy_setopt(e, CURLOPT_HEADERFUNCTION, on_header);
    curl_easy_setopt(e, CURLOPT_HEADERDATA, j);
    curl_easy_setopt(e, CURLOPT_OPENSOCKETFUNCTION, on_open_socket);
    curl_easy_setopt(e, CURLOPT_OPENSOCKETDATA, f->cfg);
    j->headers = curl_slist_append(NULL, "Accept: application/json");
    bool conditional = j->offset == 0 && j->etag[0] && j->ats != ATS_SMARTRECRUITERS;  /* a 304 on page 1 says nothing about page 2 */
    if (conditional) {
        char h[sizeof j->etag + 20];
        snprintf(h, sizeof h, "If-None-Match: %s", j->etag);
        j->headers = curl_slist_append(j->headers, h);
    }
    j->sent_etag = conditional;
    curl_easy_setopt(e, CURLOPT_HTTPHEADER, j->headers);
    j->easy = e;
    j->requests++;
    curl_multi_add_handle(f->multi, e);
    return true;
}

static void finish_transfer(jpf_fetcher *f, jpf_job *j) {
    curl_multi_remove_handle(f->multi, j->easy);
    curl_easy_cleanup(j->easy);
    curl_slist_free_all(j->headers);
    j->easy = NULL;
    j->headers = NULL;
    host_slot *h = host_get(&f->hosts, j->host);
    if (h && h->inflight > 0) h->inflight--;
    if (f->inflight > 0) f->inflight--;
}

static void done(jpf_job *j, jpf_status st, const char *err) {
    j->status = st;
    j->phase = JOB_DONE;
    if (err) snprintf(j->error, sizeof j->error, "%s", err);
    j->duration_ms = (long)((now_s() - j->started) * 1000);
}

static void retry_or_fail(jpf_job *j, const char *why) {
    static const double DELAYS[] = {2.0, 6.0};
    if (j->attempt < 2) {
        j->not_before = now_s() + DELAYS[j->attempt++];
        j->phase = JOB_WAITING;
        return;
    }
    done(j, ST_ERROR, why);
}

static void on_complete(jpf_fetcher *f, jpf_job *j, CURLcode rc) {
    char *final_url = NULL, final_host[256] = "";
    long code = 0;
    curl_easy_getinfo(j->easy, CURLINFO_RESPONSE_CODE, &code);
    curl_easy_getinfo(j->easy, CURLINFO_EFFECTIVE_URL, &final_url);
    bool host_ok = true;
    if (!f->cfg->test_origin[0] && final_url) host_ok = url_host(final_url, final_host, sizeof final_host) && jpf_host_allowed(final_host);
    finish_transfer(f, j);
    j->http_status = code;
    if (rc != CURLE_OK) {
        if (j->too_large) { done(j, ST_ERROR, "Job board response is too large."); return; }
        if (rc == CURLE_OPERATION_TIMEDOUT) { retry_or_fail(j, "Job board timed out."); return; }
        if (rc == CURLE_COULDNT_CONNECT || rc == CURLE_COULDNT_RESOLVE_HOST || rc == CURLE_RECV_ERROR || rc == CURLE_SEND_ERROR ||
            rc == CURLE_GOT_NOTHING || rc == CURLE_PARTIAL_FILE || rc == CURLE_HTTP2 || rc == CURLE_HTTP2_STREAM || rc == CURLE_SSL_CONNECT_ERROR) {
            char m[160];
            snprintf(m, sizeof m, "Job board unreachable (%s).", curl_easy_strerror(rc));
            retry_or_fail(j, m);
            return;
        }
        char m[160];
        snprintf(m, sizeof m, "Job board request failed (%s).", curl_easy_strerror(rc));
        done(j, ST_ERROR, m);
        return;
    }
    if (!host_ok) { done(j, ST_ERROR, "Redirected away from the job board's API host; refused."); return; }
    if (code == 304 && j->sent_etag) { done(j, ST_NOT_MODIFIED, NULL); return; }
    if (code == 404) { done(j, ST_NOT_FOUND, "Job board not found (the company may have moved or renamed its board)."); return; }
    if (code == 429 || code >= 500) {
        char m[96];
        snprintf(m, sizeof m, "Job board temporarily unavailable (HTTP %ld).", code);
        retry_or_fail(j, m);
        return;
    }
    if (code != 200) {
        char m[96];
        snprintf(m, sizeof m, "Job board request failed (HTTP %ld).", code);
        done(j, ST_ERROR, m);
        return;
    }
    XXH3_128bits_update(j->body_hash, j->body, j->body_len);
    long added = jpf_split(j->ats, j->body, j->body_len, &j->board);
    if (added < 0) {
        char m[240];
        snprintf(m, sizeof m, "Job board returned an unexpected response: %s.", j->board.error);
        done(j, ST_ERROR, m);
        return;
    }
    if (j->ats == ATS_SMARTRECRUITERS && (size_t)added == JPF_SR_PAGE && j->offset + JPF_SR_PAGE < JPF_SR_MAX &&
        (j->board.total_found == 0 || j->board.len < j->board.total_found)) {
        j->offset += JPF_SR_PAGE;  /* next page, same politeness rules */
        j->attempt = 0;
        j->phase = JOB_WAITING;
        j->not_before = 0;
        return;
    }
    done(j, ST_OK, NULL);
}

void jpf_fetcher_init(jpf_fetcher *f, const jpf_config *cfg) {
    memset(f, 0, sizeof *f);
    f->cfg = cfg;
    f->multi = curl_multi_init();
    curl_multi_setopt(f->multi, CURLMOPT_MAX_TOTAL_CONNECTIONS, (long)cfg->global);
    curl_multi_setopt(f->multi, CURLMOPT_MAX_HOST_CONNECTIONS, (long)cfg->per_host);
}

void jpf_fetcher_free(jpf_fetcher *f) {
    curl_multi_cleanup(f->multi);
    free(f->hosts.v);
    memset(f, 0, sizeof *f);
}

bool jpf_job_prepare(jpf_job *j) {
    char url[JPF_MAX_URL_LEN + 1];
    if (!jpf_board_url(j->ats, j->token, j->region, 0, url, sizeof url) || !url_host(url, j->host, sizeof j->host) ||
        !jpf_host_allowed(j->host)) {
        done(j, ST_ERROR, "Not a permitted job-board API host; refused.");
        return false;
    }
    jpf_board_init(&j->board);
    j->body_hash = XXH3_createState();
    XXH3_128bits_reset(j->body_hash);
    j->phase = JOB_WAITING;
    j->started = now_s();
    return true;
}

/* Runs every prepared job to completion (or until the deadline: then no new transfer starts, and transfers already
 * running finish; a job that never started is reported as ST_SKIPPED so it stays due). on_done is called as soon as
 * each job finishes, so results reach the database while other boards are still downloading. */
void jpf_fetch_all(jpf_fetcher *f, jpf_job *jobs, size_t n, double budget_s, void (*on_done)(jpf_job *, void *), void *ud,
                   volatile int *stop) {
    double deadline = now_s() + budget_s;
    size_t remaining = 0;
    for (size_t i = 0; i < n; i++)
        if (jobs[i].phase == JOB_WAITING) remaining++;
        else if (jobs[i].phase == JOB_DONE && !jobs[i].reported) {
            jobs[i].reported = true;
            if (on_done) on_done(&jobs[i], ud);
        }
    while (remaining) {
        double t = now_s();
        bool closing = t > deadline || (stop && *stop);
        for (size_t i = 0; i < n && !closing; i++) {
            jpf_job *j = &jobs[i];
            if (j->phase != JOB_WAITING || j->not_before > t || f->inflight >= f->cfg->global) continue;
            host_slot *h = host_get(&f->hosts, j->host);
            if (!h || (unsigned)h->inflight >= f->cfg->per_host || !host_take(h, t)) continue;
            if (!start(f, j)) { done(j, ST_ERROR, "Could not start the request."); }
            else { h->inflight++; f->inflight++; j->phase = JOB_RUNNING; }
        }
        if (closing) {  /* nothing new; anything not yet running stays due for the next tick */
            for (size_t i = 0; i < n; i++)
                if (jobs[i].phase == JOB_WAITING) {
                    jobs[i].phase = JOB_DONE;
                    jobs[i].status = jobs[i].board.len ? ST_ERROR : ST_SKIPPED;  /* a half-read paginated board is not complete */
                    if (jobs[i].board.len) snprintf(jobs[i].error, sizeof jobs[i].error, "Stopped before the last page.");
                }
        }
        int running = 0;
        curl_multi_perform(f->multi, &running);
        CURLMsg *msg;
        int left;
        while ((msg = curl_multi_info_read(f->multi, &left))) {
            if (msg->msg != CURLMSG_DONE) continue;
            jpf_job *j = NULL;
            curl_easy_getinfo(msg->easy_handle, CURLINFO_PRIVATE, (char **)&j);
            if (j) on_complete(f, j, msg->data.result);
        }
        remaining = 0;
        for (size_t i = 0; i < n; i++) {
            jpf_job *j = &jobs[i];
            if (j->phase == JOB_DONE && !j->reported) {
                j->reported = true;
                if (on_done) on_done(j, ud);
            }
            if (j->phase != JOB_DONE) remaining++;
        }
        if (remaining) curl_multi_poll(f->multi, NULL, 0, running ? 200 : 50, NULL);
    }
}

void jpf_job_free(jpf_job *j) {
    if (j->easy) curl_easy_cleanup(j->easy);
    curl_slist_free_all(j->headers);
    free(j->body);
    jpf_board_free(&j->board);
    if (j->body_hash) XXH3_freeState(j->body_hash);
    memset(j, 0, sizeof *j);
}

void jpf_job_body_hash(const jpf_job *j, char out[33]) {
    XXH128_canonical_t c;
    XXH128_canonicalFromHash(&c, XXH3_128bits_digest(j->body_hash));
    jpf_hex(c.digest, 16, out);
}
