/* Request parsing: one JSON object per frame, every field type-checked and bounded. Strings in the returned query point
 * into `doc`, which the caller frees after searching. Unknown fields are ignored; wrong types reject the request. */
#include <stdio.h>
#include <string.h>
#include <yyjson.h>
#include "proto.h"

static bool str_ok(yyjson_val *v, size_t max) { return yyjson_is_str(v) && yyjson_get_len(v) > 0 && yyjson_get_len(v) <= max; }

int sps_parse_request(const char *buf, size_t len, yyjson_doc **doc_out, sps_query *q, char *err, size_t n) {
    *doc_out = NULL;
    memset(q, 0, sizeof *q);
    q->posted_after_day = -1;
    q->limit = 50;
    if (!buf || len == 0 || len > SPS_MAX_FRAME) { snprintf(err, n, "empty or oversized request"); return REQ_BAD; }
    yyjson_doc *doc = yyjson_read(buf, len, 0);
    if (!doc) { snprintf(err, n, "request is not JSON"); return REQ_BAD; }
    *doc_out = doc;
    yyjson_val *root = yyjson_doc_get_root(doc);
    if (!yyjson_is_obj(root)) { snprintf(err, n, "request must be an object"); return REQ_BAD; }
    const char *m = yyjson_get_str(yyjson_obj_get(root, "method"));
    if (!m) { snprintf(err, n, "missing method"); return REQ_BAD; }
    if (!strcmp(m, "health")) return REQ_HEALTH;
    if (!strcmp(m, "stats")) return REQ_STATS;
    if (!strcmp(m, "suggest")) {
        yyjson_val *pv = yyjson_obj_get(root, "prefix");
        if (!str_ok(pv, SPS_MAX_TOKEN)) { snprintf(err, n, "suggest: prefix of 1-%d bytes", SPS_MAX_TOKEN); return REQ_BAD; }
        q->terms[0] = yyjson_get_str(pv);
        q->nterms = 1;
        yyjson_val *lv = yyjson_obj_get(root, "limit");
        q->limit = yyjson_is_int(lv) && yyjson_get_sint(lv) >= 1 && yyjson_get_sint(lv) <= 20 ? (uint32_t)yyjson_get_sint(lv) : 10;
        return REQ_SUGGEST;
    }
    if (strcmp(m, "search")) { snprintf(err, n, "unknown method"); return REQ_BAD; }

    yyjson_val *terms = yyjson_obj_get(root, "terms"), *v;
    if (terms) {
        if (!yyjson_is_arr(terms) || yyjson_arr_size(terms) > SPS_MAX_QUERY_TOKENS) { snprintf(err, n, "terms: list of at most %d strings", SPS_MAX_QUERY_TOKENS); return REQ_BAD; }
        size_t i, max;
        yyjson_arr_foreach(terms, i, max, v) {
            if (!str_ok(v, 200)) { snprintf(err, n, "terms: each term is a string of 1-200 bytes"); return REQ_BAD; }
            q->terms[q->nterms++] = yyjson_get_str(v);
        }
    }
    yyjson_val *filters = yyjson_obj_get(root, "filters"), *g;
    if (filters) {
        if (!yyjson_is_arr(filters) || yyjson_arr_size(filters) > SPS_MAX_FILTER_GROUPS) { snprintf(err, n, "filters: at most %d groups", SPS_MAX_FILTER_GROUPS); return REQ_BAD; }
        size_t i, max;
        yyjson_arr_foreach(filters, i, max, g) {
            if (!yyjson_is_arr(g) || yyjson_arr_size(g) == 0 || yyjson_arr_size(g) > SPS_MAX_FILTER_KEYS) { snprintf(err, n, "filters: each group is a list of 1-%d keys", SPS_MAX_FILTER_KEYS); return REQ_BAD; }
            size_t j, jmax;
            yyjson_arr_foreach(g, j, jmax, v) {
                if (!str_ok(v, 120)) { snprintf(err, n, "filters: keys are strings of 1-120 bytes"); return REQ_BAD; }
                q->groups[q->ngroups][q->group_len[q->ngroups]++] = yyjson_get_str(v);
            }
            q->ngroups++;
        }
    }
    v = yyjson_obj_get(root, "posted_after_day");
    if (v) { if (!yyjson_is_int(v) || yyjson_get_sint(v) < 0 || yyjson_get_sint(v) > 200000) { snprintf(err, n, "posted_after_day: day number"); return REQ_BAD; } q->posted_after_day = (int32_t)yyjson_get_sint(v); }
    yyjson_val *sal = yyjson_obj_get(root, "salary");
    if (sal) {
        yyjson_val *c = yyjson_obj_get(sal, "currency"), *mn = yyjson_obj_get(sal, "min"), *u = yyjson_obj_get(sal, "unknown_ok");
        if (!yyjson_is_obj(sal) || !str_ok(c, 3) || !yyjson_is_num(mn) || (u && !yyjson_is_bool(u))) { snprintf(err, n, "salary: {currency, min, unknown_ok}"); return REQ_BAD; }
        q->salary_currency = yyjson_get_str(c);
        q->salary_min = yyjson_get_num(mn);
        q->salary_unknown_ok = u && yyjson_get_bool(u);
    }
    v = yyjson_obj_get(root, "all_terms");
    if (v) { if (!yyjson_is_bool(v)) { snprintf(err, n, "all_terms: boolean"); return REQ_BAD; } q->require_all_terms = yyjson_get_bool(v); }
    v = yyjson_obj_get(root, "title_only");
    if (v) { if (!yyjson_is_bool(v)) { snprintf(err, n, "title_only: boolean"); return REQ_BAD; } q->title_only = yyjson_get_bool(v); }
    v = yyjson_obj_get(root, "prefix");
    if (v) { if (!yyjson_is_bool(v)) { snprintf(err, n, "prefix: boolean"); return REQ_BAD; } q->prefix = yyjson_get_bool(v); }
    v = yyjson_obj_get(root, "limit");
    if (v) { if (!yyjson_is_int(v) || yyjson_get_sint(v) < 1 || yyjson_get_sint(v) > SPS_MAX_LIMIT) { snprintf(err, n, "limit: 1-%d", SPS_MAX_LIMIT); return REQ_BAD; } q->limit = (uint32_t)yyjson_get_sint(v); }
    return REQ_SEARCH;
}
