#include <ctype.h>
#include <string.h>
#include "sps.h"

static const char *STOP[] = {"a", "an", "and", "the", "of", "to", "in", "for", "with", "on", "at", "or", "is", "are", "be",
                             "as", "by", "we", "you", "our", "your", "will", "this", "that", "from", "&", NULL};

static bool stop(const char *t, size_t n) {
    for (int i = 0; STOP[i]; i++)
        if (strlen(STOP[i]) == n && !memcmp(STOP[i], t, n)) return true;
    return false;
}

static bool tokch(unsigned char c) { return isalnum(c) || c >= 0x80 || c == '+' || c == '#'; }

size_t sps_tokenize(const char *s, size_t len, size_t max_tokens, bool drop_single, sps_token_fn fn, void *ud) {
    char buf[SPS_MAX_TOKEN + 1];
    size_t emitted = 0, i = 0;
    while (i < len) {
        while (i < len && !tokch((unsigned char)s[i])) i++;
        size_t start = i;
        while (i < len && tokch((unsigned char)s[i])) i++;
        size_t n = i - start;
        if (!n) continue;
        /* '+' and '#' only belong to a token after a letter or digit ("c++", "c#"), never alone or leading */
        while (n && (s[start] == '+' || s[start] == '#')) { start++; n--; }
        if (!n || n > SPS_MAX_TOKEN) continue;
        for (size_t k = 0; k < n; k++) buf[k] = (char)tolower((unsigned char)s[start + k]);
        buf[n] = 0;
        if ((drop_single && n == 1) || stop(buf, n)) continue;
        fn(buf, n, ud);
        if (max_tokens && ++emitted >= max_tokens) break;
    }
    return emitted;
}

size_t sps_norm_ascii(const char *s, size_t len, sps_token_fn fn, void *ud) {
    char buf[SPS_MAX_TOKEN + 1];
    size_t n = 0, emitted = 0;
    for (size_t i = 0; i <= len; i++) {
        unsigned char c = i < len ? (unsigned char)s[i] : 0;
        bool word = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
        if (word) {
            if (n < SPS_MAX_TOKEN) buf[n] = (char)tolower(c);
            n++;
            continue;
        }
        if (n && n <= SPS_MAX_TOKEN) { buf[n] = 0; fn(buf, n, ud); emitted++; }
        n = 0;
        if (c == '&') { fn("and", 3, ud); emitted++; }
    }
    return emitted;
}
