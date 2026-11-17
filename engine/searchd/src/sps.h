/* jp-searchd: JobPilot's native search server (JPSE blueprint, Phase 3).
 *
 * An in-memory index of every open posting in catalogue_postings: an inverted index over title, skills, company,
 * location and description (field-weighted BM25 impacts, precomputed per posting), CRoaring bitmaps for exact filters
 * and dense columns for dates and salaries. PostgreSQL stays the source of truth; the index is rebuilt from it at start
 * and kept current from index_outbox. Searches return posting ids and coarse scores; Python hydrates and re-ranks. */
#ifndef SPS_H
#define SPS_H

#include <pthread.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <roaring/roaring.h>

#define SPS_VERSION "0.1.0"
#define SPS_MAX_TOKEN 40
#define SPS_MAX_DESC_TOKENS 400      /* description tokens indexed per posting */
#define SPS_MAX_QUERY_TOKENS 64
#define SPS_MAX_FILTER_GROUPS 16
#define SPS_MAX_FILTER_KEYS 64
#define SPS_MAX_LIMIT 2000
#define SPS_MAX_FRAME (256 * 1024)   /* request frames; responses are bounded by SPS_MAX_LIMIT */

enum { F_TITLE, F_SKILLS, F_COMPANY, F_LOCATION, F_DESC, SPS_NFIELDS };

/* ---- text.c ---- */
typedef void (*sps_token_fn)(const char *tok, size_t len, void *ud);
/* Lower-cases ASCII, splits on anything that is not a letter, digit, '+' or '#' (UTF-8 bytes stay in tokens), drops
 * stop words; returns the number of tokens emitted (at most max_tokens; 0 = unlimited). */
size_t sps_tokenize(const char *s, size_t len, size_t max_tokens, bool drop_single, sps_token_fn fn, void *ud);

/* ---- dict.c ---- */
typedef struct { char **keys; uint32_t *vals; size_t cap, len; uint64_t seed; } sps_strmap;   /* string -> u32 */
typedef struct { int64_t *keys; uint32_t *vals; size_t cap, len; } sps_idmap;                /* int64 -> u32 */
void sps_strmap_init(sps_strmap *m, size_t expected);
void sps_strmap_free(sps_strmap *m);
bool sps_strmap_get(const sps_strmap *m, const char *key, size_t len, uint32_t *out);
bool sps_strmap_put(sps_strmap *m, const char *key, size_t len, uint32_t val);
void sps_idmap_init(sps_idmap *m, size_t expected);
void sps_idmap_free(sps_idmap *m);
bool sps_idmap_get(const sps_idmap *m, int64_t key, uint32_t *out);
bool sps_idmap_put(sps_idmap *m, int64_t key, uint32_t val);
bool sps_idmap_del(sps_idmap *m, int64_t key);

/* ---- index.c ---- */
typedef struct {
    int64_t id;                      /* catalogue_postings.id */
    int32_t revision;
    const char *text[SPS_NFIELDS];   /* title, skills (space-joined), company, location, description */
    const char *country, *work_mode, *employment_type, *seniority, *source, *currency;
    const char *remote_scope[16];
    int n_remote;
    int32_t company_id;
    int32_t posted_day;              /* days since 1970-01-01, or -1 */
    double sal_min, sal_max;         /* NAN when unknown */
} sps_doc;

typedef struct { uint32_t *docs; float *imp; uint32_t n, cap; } sps_plist;

typedef struct sps_index {
    /* documents (dense local ids; an update appends a new local id and kills the old one) */
    int64_t *pid;
    int32_t *rev, *posted_day;
    float *sal_min, *sal_max;
    uint32_t *currency;              /* filter-key id of "cur:XXX", or UINT32_MAX */
    uint32_t ndocs, dcap, nlive;
    roaring_bitmap_t *live;
    sps_idmap byid;
    /* terms */
    sps_strmap terms;
    sps_plist *lists;
    uint32_t nterms, tcap;
    /* filters */
    sps_strmap fkeys;
    roaring_bitmap_t **fbm;
    uint32_t nf, fcap;
    /* statistics for length normalisation */
    double avg_len[SPS_NFIELDS];     /* used for impacts (priors, or the last full build's measurement) */
    double sum_len[SPS_NFIELDS];
    uint64_t generation;
} sps_index;

sps_index *sps_index_new(const double *avg_len /* NULL = priors */);
void sps_index_free(sps_index *ix);
bool sps_index_upsert(sps_index *ix, const sps_doc *d);   /* idempotent by revision */
bool sps_index_remove(sps_index *ix, int64_t id);
double sps_index_dead_ratio(const sps_index *ix);
void sps_index_measured_avg(const sps_index *ix, double out[SPS_NFIELDS]);

typedef struct {
    const char *terms[SPS_MAX_QUERY_TOKENS];
    size_t nterms;
    const char *groups[SPS_MAX_FILTER_GROUPS][SPS_MAX_FILTER_KEYS];  /* OR within a group, AND across groups */
    size_t group_len[SPS_MAX_FILTER_GROUPS];
    size_t ngroups;
    int32_t posted_after_day;        /* -1: no constraint; otherwise postings with unknown dates are excluded */
    const char *salary_currency;     /* with salary_min: the posting's max (or min) pay in this currency must reach it */
    double salary_min;
    bool salary_unknown_ok;
    bool require_all_terms;
    uint32_t limit;
} sps_query;

typedef struct { int64_t id; float score; } sps_hit;
typedef struct { sps_hit *hits; uint32_t n; uint32_t candidates; } sps_result;
/* Caller holds at least a read lock. Thread-safe for concurrent readers (all scratch memory is per call). */
bool sps_search(const sps_index *ix, const sps_query *q, int32_t today_day, sps_result *out);
void sps_result_free(sps_result *r);

#endif
