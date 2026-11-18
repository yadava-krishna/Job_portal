/* jp-fetchd: JobPilot's native board crawler (JPSE blueprint, Phase 2).
 *
 * It fetches permitted employer job-board APIs politely, validates and splits each board into postings, detects which
 * postings changed, and records the result in PostgreSQL (crawl_results / crawl_result_items). It never interprets a
 * posting: the Python service parses changed postings with the same code it always used, so identities and fields are
 * identical by construction. PostgreSQL stays the source of truth; this process holds no state of its own.
 */
#ifndef JPF_H
#define JPF_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <sys/socket.h>

#define JPF_VERSION "0.1.0"
#define JPF_USER_AGENT "JobPilot/1.0.0 (job-board API reader; +https://github.com/yadava-krishna/Job_portal) jp-fetchd/" JPF_VERSION

/* Hard limits on untrusted input (blueprint section 11). */
#define JPF_MAX_BODY_BYTES   (64u * 1024u * 1024u)  /* one response; Ashby boards can be ~34 MB */
#define JPF_MAX_BOARD_BYTES  (96u * 1024u * 1024u)  /* all pages of one board together */
#define JPF_MAX_POSTINGS     20000u                 /* postings per board */
#define JPF_MAX_ID_LEN       200u
#define JPF_MAX_TOKEN_LEN    120u
#define JPF_MAX_URL_LEN      600u
#define JPF_SR_PAGE          100u                   /* SmartRecruiters page size (backend/services/ats/smartrecruiters.py) */
#define JPF_SR_MAX           1000u                  /* SmartRecruiters postings read per board */

typedef enum { ATS_GREENHOUSE, ATS_LEVER, ATS_ASHBY, ATS_SMARTRECRUITERS, ATS_RECRUITEE, ATS_UNKNOWN } jpf_ats;

jpf_ats jpf_ats_from(const char *name);
const char *jpf_ats_name(jpf_ats a);

/* ---- policy.c ---- */
bool jpf_token_ok(const char *token);                       /* same rule as ats/base.py TOKEN_RE */
bool jpf_host_allowed(const char *host);                     /* permitted ATS API hosts only */
bool jpf_host_denied(const char *host);                      /* LinkedIn, Naukri, Indeed, Glassdoor: never */
bool jpf_ip_forbidden(const struct sockaddr *sa, bool allow_loopback); /* private, loopback, link-local, metadata */
double jpf_host_rps(const char *host);
/* Builds the first-page URL for a board into buf; returns false if the token or result is not acceptable. */
bool jpf_board_url(jpf_ats ats, const char *token, const char *region, unsigned offset, char *buf, size_t n);

/* ---- hashmap.c: open addressing, linear probing, seeded hash, owns copies of keys ---- */
typedef struct { char *key; uint8_t val[16]; uint32_t mark; } jpf_slot;
typedef struct { jpf_slot *slots; size_t cap, len; uint64_t seed; } jpf_map;
void jpf_map_init(jpf_map *m, size_t expected);
void jpf_map_free(jpf_map *m);
bool jpf_map_put(jpf_map *m, const char *key, const uint8_t val[16]);   /* false only on allocation failure */
const uint8_t *jpf_map_get(const jpf_map *m, const char *key);

/* ---- split.c: board JSON -> postings ---- */
typedef struct {
    char id[JPF_MAX_ID_LEN + 1];
    uint8_t hash[16];        /* XXH3-128 of the posting's canonical (minified) JSON */
    char *json;              /* minified JSON of the posting (malloc'd) */
    size_t json_len;
} jpf_posting;

typedef struct {
    jpf_posting *items;
    size_t len, cap;
    size_t total_found;      /* SmartRecruiters: totalFound, to know whether another page exists */
    size_t last_page_len;    /* items in the last page's array (not only new ones): what pagination is decided on */
    jpf_map seen;            /* ids already taken from this board (across pages) */
    char error[160];         /* why the body was rejected, if it was */
} jpf_board;

void jpf_board_init(jpf_board *b);
void jpf_board_free(jpf_board *b);
/* Parses one response body of the given ATS and appends its postings. Returns the number of postings added in this
 * page, or -1 when the body is not the shape that API returns (b->error says why). Never trusts the input. */
long jpf_split(jpf_ats ats, const char *body, size_t len, jpf_board *b);

void jpf_hex(const uint8_t *in, size_t n, char *out);       /* out needs 2n+1 */
/* Caps the JSON parser's memory with a fixed pool (0 = the system allocator). A hostile body such as [0,0,0,...]
 * then fails to parse with an error instead of exhausting the container's memory. Call once, before any split. */
bool jpf_split_memory_limit(size_t bytes);

#endif
