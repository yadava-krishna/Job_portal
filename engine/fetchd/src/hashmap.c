#define _POSIX_C_SOURCE 200809L
/* A small string-keyed hash map for "posting id -> content hash" of one board (thousands of keys, short lived).
 * Open addressing with linear probing over a power-of-two table, load factor <= 0.7, seeded XXH3 so that board
 * contents cannot be crafted to collide. Keys are copied; values are 16-byte hashes. No deletion is needed. */
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <xxhash.h>
#include "jpf.h"

static size_t pow2_at_least(size_t n) {
    size_t c = 16;
    while (c < n) c <<= 1;
    return c;
}

void jpf_map_init(jpf_map *m, size_t expected) {
    m->cap = pow2_at_least(expected * 10 / 7 + 1);
    m->len = 0;
    m->slots = calloc(m->cap, sizeof(jpf_slot));
    if (!m->slots) m->cap = 0;
    m->seed = ((uint64_t)time(NULL) << 20) ^ (uint64_t)getpid() ^ (uint64_t)(uintptr_t)m;
}

void jpf_map_free(jpf_map *m) {
    for (size_t i = 0; i < m->cap; i++) free(m->slots[i].key);
    free(m->slots);
    m->slots = NULL;
    m->cap = m->len = 0;
}

static size_t probe(const jpf_map *m, const char *key) {
    size_t mask = m->cap - 1, i = (size_t)XXH3_64bits_withSeed(key, strlen(key), m->seed) & mask;
    while (m->slots[i].key && strcmp(m->slots[i].key, key) != 0) i = (i + 1) & mask;
    return i;
}

static bool grow(jpf_map *m) {
    jpf_map bigger = {.cap = m->cap ? m->cap * 2 : 16, .len = 0, .seed = m->seed};
    bigger.slots = calloc(bigger.cap, sizeof(jpf_slot));
    if (!bigger.slots) return false;
    for (size_t i = 0; i < m->cap; i++)
        if (m->slots[i].key) {
            size_t j = probe(&bigger, m->slots[i].key);
            bigger.slots[j] = m->slots[i];
            bigger.len++;
        }
    free(m->slots);
    *m = bigger;
    return true;
}

bool jpf_map_put(jpf_map *m, const char *key, const uint8_t val[16]) {
    if (!m->cap || (m->len + 1) * 10 > m->cap * 7) {
        if (!grow(m)) return false;
    }
    size_t i = probe(m, key);
    if (!m->slots[i].key) {
        m->slots[i].key = strdup(key);
        if (!m->slots[i].key) return false;
        m->len++;
    }
    memcpy(m->slots[i].val, val, 16);
    return true;
}

const uint8_t *jpf_map_get(const jpf_map *m, const char *key) {
    if (!m->cap) return NULL;
    size_t i = probe(m, key);
    return m->slots[i].key ? m->slots[i].val : NULL;
}
