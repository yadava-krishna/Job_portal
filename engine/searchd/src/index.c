/* The in-memory index: documents, inverted lists with precomputed BM25F impacts, filter bitmaps, and search.
 *
 * Updates never rewrite a posting list: a changed posting gets a new local doc id (appended, so every list stays
 * sorted) and its old id leaves the `live` bitmap. Dead entries are skipped at query time and dropped by the periodic
 * full rebuild (sync.c), like segment merging. */
#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "sps.h"

static const double WEIGHT[SPS_NFIELDS] = {3.0, 2.5, 1.5, 0.5, 1.0};       /* title, skills, company, location, description */
static const double PRIOR_LEN[SPS_NFIELDS] = {5.0, 10.0, 2.0, 3.0, 300.0};
#define K1 1.2
#define B 0.75

sps_index *sps_index_new(const double *avg_len) {
    sps_index *ix = calloc(1, sizeof *ix);
    if (!ix) return NULL;
    ix->live = roaring_bitmap_create();
    sps_idmap_init(&ix->byid, 1024);
    sps_strmap_init(&ix->terms, 4096);
    sps_strmap_init(&ix->fkeys, 256);
    for (int f = 0; f < SPS_NFIELDS; f++) ix->avg_len[f] = avg_len && avg_len[f] > 0 ? avg_len[f] : PRIOR_LEN[f];
    return ix;
}

void sps_index_free(sps_index *ix) {
    if (!ix) return;
    free(ix->pid); free(ix->rev); free(ix->posted_day); free(ix->sal_min); free(ix->sal_max); free(ix->currency);
    roaring_bitmap_free(ix->live);
    sps_idmap_free(&ix->byid);
    for (uint32_t t = 0; t < ix->nterms; t++) { free(ix->lists[t].docs); free(ix->lists[t].imp); }
    free(ix->lists);
    sps_strmap_free(&ix->terms);
    for (uint32_t i = 0; i < ix->nf; i++) roaring_bitmap_free(ix->fbm[i]);
    free(ix->fbm);
    sps_strmap_free(&ix->fkeys);
    free(ix);
}

static bool grow_docs(sps_index *ix) {
    if (ix->ndocs < ix->dcap) return true;
    uint32_t cap = ix->dcap ? ix->dcap * 2 : 1024;
#define RE(p) do { void *n_ = realloc(ix->p, (size_t)cap * sizeof *ix->p); if (!n_) return false; ix->p = n_; } while (0)
    RE(pid); RE(rev); RE(posted_day); RE(sal_min); RE(sal_max); RE(currency);
#undef RE
    ix->dcap = cap;
    return true;
}

static uint32_t filter_key(sps_index *ix, const char *prefix, const char *val) {
    if (!val || !*val) return UINT32_MAX;
    char k[128];
    size_t n = 0;
    for (const char *p = prefix; *p && n < sizeof k - 1; p++) k[n++] = *p;
    for (const char *p = val; *p && n < sizeof k - 1; p++) k[n++] = *p;  /* exact: values are already normalised upstream */
    k[n] = 0;
    uint32_t id;
    if (sps_strmap_get(&ix->fkeys, k, n, &id)) return id;
    if (ix->nf == ix->fcap) {
        uint32_t cap = ix->fcap ? ix->fcap * 2 : 64;
        roaring_bitmap_t **b = realloc(ix->fbm, cap * sizeof *b);
        if (!b) return UINT32_MAX;
        ix->fbm = b;
        ix->fcap = cap;
    }
    id = ix->nf;
    ix->fbm[id] = roaring_bitmap_create();
    if (!sps_strmap_put(&ix->fkeys, k, n, id)) { roaring_bitmap_free(ix->fbm[id]); return UINT32_MAX; }
    ix->nf++;
    return id;
}

static void filter_add(sps_index *ix, const char *prefix, const char *val, uint32_t doc) {
    uint32_t id = filter_key(ix, prefix, val);
    if (id != UINT32_MAX) roaring_bitmap_add(ix->fbm[id], doc);
}

/* Per-document term frequencies, collected per field before impacts are computed. */
typedef struct { uint32_t term; uint16_t tf[SPS_NFIELDS]; } tfent;
typedef struct { sps_index *ix; tfent *v; size_t n, cap; sps_strmap local; int field; uint32_t len[SPS_NFIELDS]; bool oom; } tfctx;

static uint32_t term_id(sps_index *ix, const char *tok, size_t n) {
    uint32_t id;
    if (sps_strmap_get(&ix->terms, tok, n, &id)) return id;
    if (ix->nterms == ix->tcap) {
        uint32_t cap = ix->tcap ? ix->tcap * 2 : 4096;
        sps_plist *l = realloc(ix->lists, cap * sizeof *l);
        if (!l) return UINT32_MAX;
        memset(l + ix->tcap, 0, (cap - ix->tcap) * sizeof *l);
        ix->lists = l;
        ix->tcap = cap;
    }
    id = ix->nterms;
    if (!sps_strmap_put(&ix->terms, tok, n, id)) return UINT32_MAX;
    ix->nterms++;
    return id;
}

static void on_token(const char *tok, size_t n, void *ud) {
    tfctx *c = ud;
    c->len[c->field]++;
    uint32_t slot;
    if (!sps_strmap_get(&c->local, tok, n, &slot)) {
        uint32_t t = term_id(c->ix, tok, n);
        if (t == UINT32_MAX) { c->oom = true; return; }
        if (c->n == c->cap) {
            size_t cap = c->cap ? c->cap * 2 : 64;
            tfent *v = realloc(c->v, cap * sizeof *v);
            if (!v) { c->oom = true; return; }
            c->v = v;
            c->cap = cap;
        }
        slot = (uint32_t)c->n++;
        memset(&c->v[slot], 0, sizeof c->v[slot]);
        c->v[slot].term = t;
        if (!sps_strmap_put(&c->local, tok, n, slot)) { c->oom = true; return; }
    }
    if (c->v[slot].tf[c->field] < UINT16_MAX) c->v[slot].tf[c->field]++;
}

static bool plist_push(sps_plist *l, uint32_t doc, float imp) {
    if (l->n == l->cap) {
        uint32_t cap = l->cap ? l->cap * 2 : 4;
        uint32_t *d = realloc(l->docs, cap * sizeof *d);
        if (!d) return false;
        l->docs = d;
        float *f = realloc(l->imp, cap * sizeof *f);
        if (!f) return false;
        l->imp = f;
        l->cap = cap;
    }
    l->docs[l->n] = doc;
    l->imp[l->n++] = imp;
    return true;
}

typedef struct { sps_index *ix; uint32_t doc; sps_strmap seen; bool oom; } tctx;

static void on_title_word(const char *w, size_t n, void *ud) {
    tctx *c = ud;
    char key[SPS_MAX_TOKEN + 3] = "t:";
    memcpy(key + 2, w, n);
    key[n + 2] = 0;
    uint32_t dummy;
    if (sps_strmap_get(&c->seen, key, n + 2, &dummy)) return;
    sps_strmap_put(&c->seen, key, n + 2, 1);
    uint32_t t = term_id(c->ix, key, n + 2);
    if (t == UINT32_MAX || !plist_push(&c->ix->lists[t], c->doc, 1.0f)) c->oom = true;
}

bool sps_index_upsert(sps_index *ix, const sps_doc *d) {
    uint32_t old;
    bool had = sps_idmap_get(&ix->byid, d->id, &old);
    if (had && ix->rev[old] >= d->revision && roaring_bitmap_contains(ix->live, old)) return true;  /* already current */
    if (!grow_docs(ix)) return false;
    uint32_t doc = ix->ndocs;
    tfctx c = {.ix = ix};
    sps_strmap_init(&c.local, 64);
    for (int f = 0; f < SPS_NFIELDS; f++) {
        c.field = f;
        const char *t = d->text[f] ? d->text[f] : "";
        sps_tokenize(t, strlen(t), f == F_DESC ? SPS_MAX_DESC_TOKENS : 0, f == F_DESC, on_token, &c);
    }
    bool ok = !c.oom;
    for (size_t i = 0; ok && i < c.n; i++) {
        double imp = 0;
        for (int f = 0; f < SPS_NFIELDS; f++) {
            double tf = c.v[i].tf[f];
            if (!tf) continue;
            double norm = 1.0 - B + B * (double)c.len[f] / ix->avg_len[f];
            imp += WEIGHT[f] * tf * (K1 + 1.0) / (tf + K1 * norm);
        }
        ok = plist_push(&ix->lists[c.v[i].term], doc, (float)imp);
    }
    free(c.v);
    sps_strmap_free(&c.local);
    if (ok) {  /* title words, normalised exactly like JobPilot's title matching, for candidate retrieval */
        tctx tc = {.ix = ix, .doc = doc};
        sps_strmap_init(&tc.seen, 16);
        const char *t = d->text[F_TITLE] ? d->text[F_TITLE] : "";
        sps_norm_ascii(t, strlen(t), on_title_word, &tc);
        sps_strmap_free(&tc.seen);
        ok = !tc.oom;
    }
    if (!ok) return false;  /* partially pushed entries point at a doc that never becomes live: harmless */
    ix->pid[doc] = d->id;
    ix->rev[doc] = d->revision;
    ix->posted_day[doc] = d->posted_day;
    ix->sal_min[doc] = (float)d->sal_min;
    ix->sal_max[doc] = (float)d->sal_max;
    ix->currency[doc] = filter_key(ix, "cur:", d->currency);
    if (ix->currency[doc] != UINT32_MAX) roaring_bitmap_add(ix->fbm[ix->currency[doc]], doc);
    filter_add(ix, "country:", d->country, doc);
    filter_add(ix, "mode:", d->work_mode, doc);
    filter_add(ix, "type:", d->employment_type, doc);
    filter_add(ix, "seniority:", d->seniority, doc);
    filter_add(ix, "source:", d->source, doc);
    for (int i = 0; i < d->n_remote && i < 16; i++) filter_add(ix, "remote:", d->remote_scope[i], doc);
    if (d->n_remote) filter_add(ix, "remote:", "any", doc);
    if (d->company_id > 0) {
        char cid[24];
        snprintf(cid, sizeof cid, "%d", d->company_id);
        filter_add(ix, "company:", cid, doc);
    }
    ix->ndocs++;
    for (int f = 0; f < SPS_NFIELDS; f++) ix->sum_len[f] += c.len[f];
    if (had && roaring_bitmap_contains(ix->live, old)) { roaring_bitmap_remove(ix->live, old); ix->nlive--; }
    roaring_bitmap_add(ix->live, doc);
    ix->nlive++;
    sps_idmap_put(&ix->byid, d->id, doc);
    ix->generation++;
    return true;
}

bool sps_index_remove(sps_index *ix, int64_t id) {
    uint32_t doc;
    if (!sps_idmap_get(&ix->byid, id, &doc)) return false;
    if (roaring_bitmap_contains(ix->live, doc)) { roaring_bitmap_remove(ix->live, doc); ix->nlive--; }
    sps_idmap_del(&ix->byid, id);
    ix->generation++;
    return true;
}

double sps_index_dead_ratio(const sps_index *ix) { return ix->ndocs ? 1.0 - (double)ix->nlive / ix->ndocs : 0.0; }

void sps_index_measured_avg(const sps_index *ix, double out[SPS_NFIELDS]) {
    for (int f = 0; f < SPS_NFIELDS; f++) out[f] = ix->ndocs ? ix->sum_len[f] / ix->ndocs : PRIOR_LEN[f];
}

/* ---- search ---- */

typedef struct { uint64_t *w; uint32_t n; } bitset;
static bool bs_has(const bitset *b, uint32_t i) { return i < b->n && (b->w[i >> 6] >> (i & 63) & 1); }
static bool to_bitset(uint32_t v, void *ud) { bitset *b = ud; b->w[v >> 6] |= 1ull << (v & 63); return true; }

/* Total order: higher score first, then lower posting id. Used by the heap AND the final sort, so a cut-off between
 * equal scores always keeps the same postings regardless of where updates placed them in the index. */
static bool worse(sps_hit a, sps_hit b) { return a.score < b.score || (a.score == b.score && a.id > b.id); }

static void heap_push(sps_hit *h, uint32_t *n, uint32_t k, sps_hit x) {  /* min-heap of the k best by `worse` */
    if (*n < k) {
        uint32_t i = (*n)++;
        h[i] = x;
        while (i && worse(h[i], h[(i - 1) / 2])) { sps_hit t = h[i]; h[i] = h[(i - 1) / 2]; h[(i - 1) / 2] = t; i = (i - 1) / 2; }
        return;
    }
    if (!worse(h[0], x)) return;
    h[0] = x;
    for (uint32_t i = 0;;) {
        uint32_t l = 2 * i + 1, r = l + 1, m = i;
        if (l < k && worse(h[l], h[m])) m = l;
        if (r < k && worse(h[r], h[m])) m = r;
        if (m == i) break;
        sps_hit t = h[i]; h[i] = h[m]; h[m] = t; i = m;
    }
}

static int by_score_desc(const void *a, const void *b) {
    const sps_hit *x = a, *y = b;
    if (x->score != y->score) return x->score < y->score ? 1 : -1;
    return x->id < y->id ? -1 : x->id > y->id;  /* deterministic order for equal scores */
}

#define QTERMS 4096  /* after prefix expansion; never silently truncated below what the index can hold */
typedef struct { const sps_index *ix; uint32_t term[QTERMS]; size_t n; bool missing, overflow; } qtok;
static void on_qtoken(const char *tok, size_t n, void *ud) {
    qtok *q = ud;
    uint32_t id;
    if (!sps_strmap_get(&q->ix->terms, tok, n, &id)) { q->missing = true; return; }
    for (size_t i = 0; i < q->n; i++) if (q->term[i] == id) return;
    if (q->n < QTERMS) q->term[q->n++] = id; else q->overflow = true;
}

static void add_term(qtok *q, uint32_t id) {
    for (size_t i = 0; i < q->n; i++) if (q->term[i] == id) return;
    if (q->n < QTERMS) q->term[q->n++] = id; else q->overflow = true;
}

/* Candidate-mode words: space-separated, already normalised; "t:" namespace; optional prefix expansion. */
static void title_terms(const sps_index *ix, const char *s, bool prefix, qtok *q) {
    size_t len = strlen(s);
    for (size_t i = 0; i < len;) {
        while (i < len && s[i] == ' ') i++;
        size_t st = i;
        while (i < len && s[i] != ' ') i++;
        size_t n = i - st;
        if (!n || n > SPS_MAX_TOKEN) continue;
        char key[SPS_MAX_TOKEN + 3] = "t:";
        memcpy(key + 2, s + st, n);
        key[n + 2] = 0;
        uint32_t id;
        bool found = sps_strmap_get(&ix->terms, key, n + 2, &id);
        if (found) add_term(q, id);
        if (prefix && n >= 5) {  /* every title word starting with it */
            for (size_t k = 0; k < ix->terms.cap; k++) {
                const char *t = ix->terms.keys[k];
                if (t && strncmp(t, key, n + 2) == 0 && t[n + 2]) add_term(q, ix->terms.vals[k]);
            }
        } else if (!found) {
            q->missing = true;
        }
    }
}

size_t sps_suggest(const sps_index *ix, const char *prefix, char out[][SPS_MAX_TOKEN + 1], size_t max) {
    char key[SPS_MAX_TOKEN + 3] = "t:";
    size_t n = 0;
    for (const char *p = prefix; *p && n < SPS_MAX_TOKEN; p++) {
        char c = *p >= 'A' && *p <= 'Z' ? (char)(*p + 32) : *p;
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) key[2 + n++] = c;
    }
    key[2 + n] = 0;
    if (n < 2 || !max) return 0;
    uint32_t best_df[32] = {0};
    const char *best[32];
    size_t cnt = 0, lim = max < 32 ? max : 32;
    for (size_t k = 0; k < ix->terms.cap; k++) {
        const char *t = ix->terms.keys[k];
        if (!t || strncmp(t, key, n + 2) != 0) continue;
        uint32_t df = ix->lists[ix->terms.vals[k]].n;
        size_t pos = cnt < lim ? cnt++ : lim;
        if (pos == lim && df <= best_df[lim - 1]) continue;
        if (pos == lim) pos = lim - 1;
        while (pos > 0 && best_df[pos - 1] < df) { best_df[pos] = best_df[pos - 1]; best[pos] = best[pos - 1]; pos--; }
        best_df[pos] = df;
        best[pos] = t;
    }
    for (size_t i = 0; i < cnt; i++) snprintf(out[i], SPS_MAX_TOKEN + 1, "%s", best[i] + 2);
    return cnt;
}

bool sps_search(const sps_index *ix, const sps_query *q, int32_t today, sps_result *out) {
    memset(out, 0, sizeof *out);
    uint32_t limit = q->limit ? (q->limit > SPS_MAX_LIMIT ? SPS_MAX_LIMIT : q->limit) : 50;
    /* 1. exact filters: live AND (OR of each group), smallest groups first would not change the result, only speed */
    roaring_bitmap_t *cand = roaring_bitmap_copy(ix->live);
    if (!cand) return false;
    for (size_t g = 0; g < q->ngroups; g++) {
        roaring_bitmap_t *any = roaring_bitmap_create();
        for (size_t k = 0; k < q->group_len[g]; k++) {
            uint32_t id;
            const char *key = q->groups[g][k];
            if (sps_strmap_get(&ix->fkeys, key, strlen(key), &id)) roaring_bitmap_or_inplace(any, ix->fbm[id]);
        }
        roaring_bitmap_and_inplace(cand, any);
        roaring_bitmap_free(any);
    }
    uint32_t cur_id = UINT32_MAX;
    bool cur_known = q->salary_currency && *q->salary_currency;
    if (cur_known) {
        char k[16];
        snprintf(k, sizeof k, "cur:%s", q->salary_currency);
        uint32_t id;
        if (sps_strmap_get(&ix->fkeys, k, strlen(k), &id)) cur_id = id;
    }
    bitset bs = {.n = ix->ndocs, .w = calloc((ix->ndocs >> 6) + 1, sizeof(uint64_t))};
    if (!bs.w) { roaring_bitmap_free(cand); return false; }
    roaring_iterate(cand, to_bitset, &bs);
    roaring_bitmap_free(cand);
    /* numeric constraints are checked per candidate (exact, never fuzzy) */
#define NUMERIC_OK(d) ( \
    (q->posted_after_day < 0 || (ix->posted_day[d] >= 0 && ix->posted_day[d] >= q->posted_after_day)) && \
    (!cur_known || q->salary_min <= 0 || \
        ((ix->currency[d] == cur_id && cur_id != UINT32_MAX) ? \
            ((isnan(ix->sal_max[d]) ? ix->sal_min[d] : ix->sal_max[d]) >= q->salary_min) : \
            (q->salary_unknown_ok && ix->currency[d] == UINT32_MAX))))
    sps_hit *heap = malloc(limit * sizeof *heap);
    uint32_t hn = 0;
    if (!heap) { free(bs.w); return false; }
    qtok qt = {.ix = ix};
    for (size_t i = 0; i < q->nterms; i++) {
        if (q->title_only) title_terms(ix, q->terms[i], q->prefix, &qt);
        else sps_tokenize(q->terms[i], strlen(q->terms[i]), 0, false, on_qtoken, &qt);
    }
    if (qt.overflow) {  /* more distinct words than QTERMS: refuse rather than return an incomplete candidate set */
        free(heap);
        free(bs.w);
        return false;
    }
    if (q->nterms == 0) {
        /* 2a. no words: newest first among the candidates */
        for (uint32_t d = 0; d < ix->ndocs; d++)
            if (bs_has(&bs, d) && NUMERIC_OK(d)) {
                out->candidates++;
                double fresh = ix->posted_day[d] >= 0 ? ix->posted_day[d] : 0;
                heap_push(heap, &hn, limit, (sps_hit){ix->pid[d], (float)fresh});
            }
    } else if (!(q->require_all_terms && qt.missing) && qt.n) {
        /* 2b. term-at-a-time BM25F accumulation over the candidates */
        float *acc = calloc(ix->ndocs ? ix->ndocs : 1, sizeof *acc);
        uint8_t *hits = q->require_all_terms ? calloc(ix->ndocs ? ix->ndocs : 1, 1) : NULL;
        if (!acc || (q->require_all_terms && !hits)) { free(acc); free(hits); free(heap); free(bs.w); return false; }
        double N = ix->nlive ? ix->nlive : 1;
        for (size_t t = 0; t < qt.n; t++) {
            const sps_plist *l = &ix->lists[qt.term[t]];
            double idf = log(1.0 + (N - l->n + 0.5) / (l->n + 0.5));
            if (idf < 0.01) idf = 0.01;
            for (uint32_t i = 0; i < l->n; i++) {
                uint32_t d = l->docs[i];
                if (!bs_has(&bs, d)) continue;
                acc[d] += (float)(idf * l->imp[i]);
                if (hits && hits[d] < 255) hits[d]++;
            }
        }
        for (uint32_t d = 0; d < ix->ndocs; d++) {
            if (acc[d] <= 0 || (hits && hits[d] < qt.n) || !NUMERIC_OK(d)) continue;
            out->candidates++;
            double age = ix->posted_day[d] >= 0 ? today - ix->posted_day[d] : 120;
            double fresh = age < 0 ? 1.0 : (age > 60 ? 0.0 : 1.0 - age / 60.0);
            heap_push(heap, &hn, limit, (sps_hit){ix->pid[d], (float)(acc[d] * (1.0 + 0.1 * fresh))});  /* bounded bonus */
        }
        free(acc);
        free(hits);
    }
#undef NUMERIC_OK
    free(bs.w);
    qsort(heap, hn, sizeof *heap, by_score_desc);
    out->hits = heap;
    out->n = hn;
    return true;
}

void sps_result_free(sps_result *r) { free(r->hits); memset(r, 0, sizeof *r); }
