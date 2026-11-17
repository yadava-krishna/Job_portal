/* Board JSON -> postings, for each permitted ATS API shape. Input is untrusted: every length is bounded, every value
 * is type-checked, and anything unexpected rejects the whole body (the board is then retried, never half-applied).
 *
 * The posting objects are kept as minified JSON; the Python service parses them with backend/services/ats/<ats>.py.
 * An item without a usable id is dropped here exactly as parse_job drops it (`not raw.get("id")`). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <xxhash.h>
#include <yyjson.h>
#include "jpf.h"

void jpf_board_init(jpf_board *b) {
    memset(b, 0, sizeof *b);
    jpf_map_init(&b->seen, 256);
}

void jpf_board_free(jpf_board *b) {
    for (size_t i = 0; i < b->len; i++) free(b->items[i].json);
    free(b->items);
    jpf_map_free(&b->seen);
    memset(b, 0, sizeof *b);
}

static bool id_of(yyjson_val *v, char *out, size_t n) {
    if (yyjson_is_str(v)) {
        size_t len = yyjson_get_len(v);
        const char *s = yyjson_get_str(v);
        if (len == 0 || len >= n) return false;
        for (size_t i = 0; i < len; i++)
            if ((unsigned char)s[i] < 0x20 || s[i] == 0x7f) return false;  /* ids become keys and log lines */
        memcpy(out, s, len);
        out[len] = 0;
        return true;
    }
    if (yyjson_is_uint(v)) { uint64_t u = yyjson_get_uint(v); return u != 0 && snprintf(out, n, "%llu", (unsigned long long)u) > 0; }
    if (yyjson_is_sint(v)) { int64_t s = yyjson_get_sint(v); return s != 0 && snprintf(out, n, "%lld", (long long)s) > 0; }
    return false;  /* null, false, float, object: parse_job would not produce a stable key from these */
}

static bool push(jpf_board *b, const char *id, char *json, size_t len) {
    if (b->len >= JPF_MAX_POSTINGS) { free(json); return false; }
    if (b->len == b->cap) {
        size_t cap = b->cap ? b->cap * 2 : 64;
        jpf_posting *p = realloc(b->items, cap * sizeof *p);
        if (!p) { free(json); return false; }
        b->items = p;
        b->cap = cap;
    }
    jpf_posting *p = &b->items[b->len++];
    snprintf(p->id, sizeof p->id, "%s", id);
    p->json = json;
    p->json_len = len;
    XXH128_canonical_t c;
    XXH128_canonicalFromHash(&c, XXH3_128bits(json, len));
    memcpy(p->hash, c.digest, 16);
    return true;
}

long jpf_split(jpf_ats ats, const char *body, size_t len, jpf_board *b) {
    b->error[0] = 0;
    if (!body || len == 0 || len > JPF_MAX_BODY_BYTES) { snprintf(b->error, sizeof b->error, "empty or oversized body"); return -1; }
    yyjson_read_err err;
    yyjson_doc *doc = yyjson_read_opts((char *)body, len, YYJSON_READ_NOFLAG, NULL, &err);
    if (!doc) { snprintf(b->error, sizeof b->error, "not JSON (%s at %zu)", err.msg, err.pos); return -1; }
    yyjson_val *root = yyjson_doc_get_root(doc), *arr = NULL;
    switch (ats) {
    case ATS_GREENHOUSE: case ATS_ASHBY: arr = yyjson_is_obj(root) ? yyjson_obj_get(root, "jobs") : NULL; break;
    case ATS_LEVER: arr = root; break;
    case ATS_RECRUITEE: arr = yyjson_is_obj(root) ? yyjson_obj_get(root, "offers") : NULL; break;
    case ATS_SMARTRECRUITERS:
        if (yyjson_is_obj(root)) {
            arr = yyjson_obj_get(root, "content");
            yyjson_val *tf = yyjson_obj_get(root, "totalFound");
            if (yyjson_is_uint(tf)) b->total_found = (size_t)yyjson_get_uint(tf);
        }
        break;
    default: break;
    }
    if (!yyjson_is_arr(arr)) {
        snprintf(b->error, sizeof b->error, "unexpected %s response shape", jpf_ats_name(ats));
        yyjson_doc_free(doc);
        return -1;
    }
    long added = 0;
    size_t idx, max;
    yyjson_val *item;
    yyjson_arr_foreach(arr, idx, max, item) {
        char id[JPF_MAX_ID_LEN + 1];
        if (!yyjson_is_obj(item) || !id_of(yyjson_obj_get(item, "id"), id, sizeof id)) continue;
        if (jpf_map_get(&b->seen, id)) continue;  /* a board listing one requisition twice keeps the first, like the Python applier */
        size_t jl = 0;
        char *json = yyjson_val_write(item, YYJSON_WRITE_NOFLAG, &jl);
        if (!json) { snprintf(b->error, sizeof b->error, "out of memory"); yyjson_doc_free(doc); return -1; }
        if (!push(b, id, json, jl)) {
            snprintf(b->error, sizeof b->error, "more than %u postings", JPF_MAX_POSTINGS);
            yyjson_doc_free(doc);
            return -1;
        }
        if (!jpf_map_put(&b->seen, id, b->items[b->len - 1].hash)) {
            snprintf(b->error, sizeof b->error, "out of memory");
            yyjson_doc_free(doc);
            return -1;
        }
        added++;
    }
    yyjson_doc_free(doc);
    return added;
}
