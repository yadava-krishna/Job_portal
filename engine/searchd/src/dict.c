/* Hash maps for the index: string -> u32 (terms, filter keys) and int64 -> u32 (posting id -> local doc id).
 * Open addressing, linear probing, power-of-two tables kept at most 70% full; seeded hashing for string keys.
 * The id map supports deletion with backward-shift (no tombstones). */
#define _POSIX_C_SOURCE 200809L
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <xxhash.h>
#include "sps.h"

static size_t pow2(size_t n) { size_t c = 16; while (c < n) c <<= 1; return c; }

void sps_strmap_init(sps_strmap *m, size_t expected) {
    m->cap = pow2(expected * 10 / 7 + 1);
    m->len = 0;
    m->keys = calloc(m->cap, sizeof *m->keys);
    m->vals = calloc(m->cap, sizeof *m->vals);
    m->seed = ((uint64_t)time(NULL) << 21) ^ (uint64_t)getpid() ^ (uint64_t)(uintptr_t)m;
}

void sps_strmap_free(sps_strmap *m) {
    for (size_t i = 0; i < m->cap; i++) free(m->keys[i]);
    free(m->keys);
    free(m->vals);
    memset(m, 0, sizeof *m);
}

static size_t sprobe(const sps_strmap *m, const char *k, size_t n) {
    size_t mask = m->cap - 1, i = (size_t)XXH3_64bits_withSeed(k, n, m->seed) & mask;
    while (m->keys[i] && (strlen(m->keys[i]) != n || memcmp(m->keys[i], k, n))) i = (i + 1) & mask;
    return i;
}

bool sps_strmap_get(const sps_strmap *m, const char *k, size_t n, uint32_t *out) {
    if (!m->cap) return false;
    size_t i = sprobe(m, k, n);
    if (!m->keys[i]) return false;
    *out = m->vals[i];
    return true;
}

static bool sgrow(sps_strmap *m) {
    sps_strmap b = {.cap = m->cap * 2, .seed = m->seed};
    b.keys = calloc(b.cap, sizeof *b.keys);
    b.vals = calloc(b.cap, sizeof *b.vals);
    if (!b.keys || !b.vals) { free(b.keys); free(b.vals); return false; }
    for (size_t i = 0; i < m->cap; i++)
        if (m->keys[i]) {
            size_t j = sprobe(&b, m->keys[i], strlen(m->keys[i]));
            b.keys[j] = m->keys[i];
            b.vals[j] = m->vals[i];
            b.len++;
        }
    free(m->keys);
    free(m->vals);
    *m = b;
    return true;
}

bool sps_strmap_put(sps_strmap *m, const char *k, size_t n, uint32_t v) {
    if ((m->len + 1) * 10 > m->cap * 7 && !sgrow(m)) return false;
    size_t i = sprobe(m, k, n);
    if (!m->keys[i]) {
        char *c = malloc(n + 1);
        if (!c) return false;
        memcpy(c, k, n);
        c[n] = 0;
        m->keys[i] = c;
        m->len++;
    }
    m->vals[i] = v;
    return true;
}

#define EMPTY INT64_MIN
static size_t ihash(int64_t k, size_t mask) { return (size_t)XXH3_64bits(&k, sizeof k) & mask; }

void sps_idmap_init(sps_idmap *m, size_t expected) {
    m->cap = pow2(expected * 10 / 7 + 1);
    m->len = 0;
    m->keys = malloc(m->cap * sizeof *m->keys);
    m->vals = malloc(m->cap * sizeof *m->vals);
    for (size_t i = 0; m->keys && i < m->cap; i++) m->keys[i] = EMPTY;
}

void sps_idmap_free(sps_idmap *m) { free(m->keys); free(m->vals); memset(m, 0, sizeof *m); }

static size_t iprobe(const sps_idmap *m, int64_t k) {
    size_t mask = m->cap - 1, i = ihash(k, mask);
    while (m->keys[i] != EMPTY && m->keys[i] != k) i = (i + 1) & mask;
    return i;
}

bool sps_idmap_get(const sps_idmap *m, int64_t k, uint32_t *out) {
    if (!m->cap || k == EMPTY) return false;
    size_t i = iprobe(m, k);
    if (m->keys[i] == EMPTY) return false;
    *out = m->vals[i];
    return true;
}

static bool igrow(sps_idmap *m) {
    sps_idmap b;
    sps_idmap_init(&b, m->cap);  /* doubles: init sizes for 70% of cap*10/7 */
    if (!b.keys || !b.vals) { sps_idmap_free(&b); return false; }
    for (size_t i = 0; i < m->cap; i++)
        if (m->keys[i] != EMPTY) {
            size_t j = iprobe(&b, m->keys[i]);
            b.keys[j] = m->keys[i];
            b.vals[j] = m->vals[i];
            b.len++;
        }
    sps_idmap_free(m);
    *m = b;
    return true;
}

bool sps_idmap_put(sps_idmap *m, int64_t k, uint32_t v) {
    if (k == EMPTY) return false;
    if ((m->len + 1) * 10 > m->cap * 7 && !igrow(m)) return false;
    size_t i = iprobe(m, k);
    if (m->keys[i] == EMPTY) { m->keys[i] = k; m->len++; }
    m->vals[i] = v;
    return true;
}

bool sps_idmap_del(sps_idmap *m, int64_t k) {
    if (!m->cap || k == EMPTY) return false;
    size_t mask = m->cap - 1, i = iprobe(m, k);
    if (m->keys[i] == EMPTY) return false;
    m->keys[i] = EMPTY;
    m->len--;
    for (size_t j = (i + 1) & mask; m->keys[j] != EMPTY; j = (j + 1) & mask) {  /* backward-shift deletion */
        size_t home = ihash(m->keys[j], mask);
        bool movable = (i <= j) ? (home <= i || home > j) : (home <= i && home > j);
        if (movable) { m->keys[i] = m->keys[j]; m->vals[i] = m->vals[j]; m->keys[j] = EMPTY; i = j; }
    }
    return true;
}
