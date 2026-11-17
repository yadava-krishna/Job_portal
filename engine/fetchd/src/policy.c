#define _GNU_SOURCE
#include <arpa/inet.h>
#include <ctype.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include "jpf.h"

jpf_ats jpf_ats_from(const char *n) {
    if (!n) return ATS_UNKNOWN;
    if (!strcmp(n, "greenhouse")) return ATS_GREENHOUSE;
    if (!strcmp(n, "lever")) return ATS_LEVER;
    if (!strcmp(n, "ashby")) return ATS_ASHBY;
    if (!strcmp(n, "smartrecruiters")) return ATS_SMARTRECRUITERS;
    if (!strcmp(n, "recruitee")) return ATS_RECRUITEE;
    return ATS_UNKNOWN;
}

const char *jpf_ats_name(jpf_ats a) {
    static const char *names[] = {"greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "unknown"};
    return names[a <= ATS_UNKNOWN ? a : ATS_UNKNOWN];
}

/* ^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$ */
bool jpf_token_ok(const char *t) {
    if (!t || !isalnum((unsigned char)t[0])) return false;
    size_t n = strlen(t);
    if (n > JPF_MAX_TOKEN_LEN) return false;
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)t[i];
        if (!(isalnum(c) || c == '.' || c == '_' || c == '-')) return false;
    }
    return strstr(t, "..") == NULL;
}

static bool ends_with(const char *s, const char *suffix) {
    size_t a = strlen(s), b = strlen(suffix);
    return a >= b && strcasecmp(s + a - b, suffix) == 0;
}

static const char *DENIED[] = {"linkedin.com", "naukri.com", "indeed.com", "indeed.co.in", "glassdoor.com", "glassdoor.co.in", NULL};

bool jpf_host_denied(const char *host) {
    if (!host) return true;
    for (int i = 0; DENIED[i]; i++) {
        size_t hl = strlen(host), dl = strlen(DENIED[i]);
        if (!strcasecmp(host, DENIED[i])) return true;
        if (hl > dl && host[hl - dl - 1] == '.' && ends_with(host, DENIED[i])) return true;
    }
    return false;
}

bool jpf_host_allowed(const char *host) {
    if (!host || jpf_host_denied(host)) return false;
    static const char *EXACT[] = {"boards-api.greenhouse.io", "api.lever.co", "api.eu.lever.co", "api.ashbyhq.com",
                                  "api.smartrecruiters.com", NULL};
    for (int i = 0; EXACT[i]; i++)
        if (!strcasecmp(host, EXACT[i])) return true;
    /* <company>.recruitee.com, one label only */
    if (ends_with(host, ".recruitee.com")) {
        size_t label = strlen(host) - strlen(".recruitee.com");
        if (label == 0 || label > 63) return false;
        for (size_t i = 0; i < label; i++)
            if (!(isalnum((unsigned char)host[i]) || host[i] == '-')) return false;
        return true;
    }
    return false;
}

double jpf_host_rps(const char *host) {
    if (!host) return 1.0;
    if (!strcasecmp(host, "boards-api.greenhouse.io")) return 3.0;
    if (!strcasecmp(host, "api.ashbyhq.com")) return 3.0;
    if (!strcasecmp(host, "api.smartrecruiters.com")) return 2.0;
    return 1.0;  /* Lever (large, slow responses), Recruitee subdomains, anything else */
}

bool jpf_ip_forbidden(const struct sockaddr *sa, bool allow_loopback) {
    if (!sa) return true;
    if (sa->sa_family == AF_INET) {
        uint32_t a = ntohl(((const struct sockaddr_in *)sa)->sin_addr.s_addr);
        uint8_t o1 = a >> 24, o2 = (a >> 16) & 0xff;
        if (o1 == 127) return !allow_loopback;
        if (o1 == 0 || o1 == 10) return true;                       /* this network, private */
        if (o1 == 100 && (o2 & 0xc0) == 64) return true;            /* carrier-grade NAT 100.64/10 */
        if (o1 == 169 && o2 == 254) return true;                    /* link-local, cloud metadata */
        if (o1 == 172 && (o2 & 0xf0) == 16) return true;            /* 172.16/12 (Docker networks too) */
        if (o1 == 192 && o2 == 168) return true;
        if (o1 == 192 && o2 == 0 && ((a >> 8) & 0xff) == 0) return true;
        if (o1 >= 224) return true;                                 /* multicast, reserved, broadcast */
        return false;
    }
    if (sa->sa_family == AF_INET6) {
        const struct in6_addr *a6 = &((const struct sockaddr_in6 *)sa)->sin6_addr;
        if (IN6_IS_ADDR_LOOPBACK(a6)) return !allow_loopback;
        if (IN6_IS_ADDR_UNSPECIFIED(a6) || IN6_IS_ADDR_LINKLOCAL(a6) || IN6_IS_ADDR_SITELOCAL(a6) || IN6_IS_ADDR_MULTICAST(a6))
            return true;
        if ((a6->s6_addr[0] & 0xfe) == 0xfc) return true;           /* unique local fc00::/7 */
        if (IN6_IS_ADDR_V4MAPPED(a6) || IN6_IS_ADDR_V4COMPAT(a6)) {
            struct sockaddr_in v4 = {.sin_family = AF_INET};
            memcpy(&v4.sin_addr, &a6->s6_addr[12], 4);
            return jpf_ip_forbidden((const struct sockaddr *)&v4, allow_loopback);
        }
        return false;
    }
    return true;
}

bool jpf_board_url(jpf_ats ats, const char *token, const char *region, unsigned offset, char *buf, size_t n) {
    if (!jpf_token_ok(token)) return false;
    int w = -1;
    switch (ats) {
    case ATS_GREENHOUSE: w = snprintf(buf, n, "https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true", token); break;
    case ATS_LEVER:
        w = snprintf(buf, n, "https://%s/v0/postings/%s?mode=json",
                     region && !strcasecmp(region, "eu") ? "api.eu.lever.co" : "api.lever.co", token);
        break;
    case ATS_ASHBY: w = snprintf(buf, n, "https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=true", token); break;
    case ATS_SMARTRECRUITERS: {
        char country[16] = "";
        if (region && strlen(region) == 2 && isalpha((unsigned char)region[0]) && isalpha((unsigned char)region[1]))
            snprintf(country, sizeof country, "&country=%c%c", tolower((unsigned char)region[0]), tolower((unsigned char)region[1]));
        w = snprintf(buf, n, "https://api.smartrecruiters.com/v1/companies/%s/postings?limit=%u&offset=%u%s", token, JPF_SR_PAGE,
                     offset, country);
        break;
    }
    case ATS_RECRUITEE: {
        char lower[JPF_MAX_TOKEN_LEN + 1];
        size_t i = 0;
        for (; token[i] && i < JPF_MAX_TOKEN_LEN; i++) {
            if (!(isalnum((unsigned char)token[i]) || token[i] == '-')) return false;  /* a DNS label */
            lower[i] = (char)tolower((unsigned char)token[i]);
        }
        lower[i] = 0;
        w = snprintf(buf, n, "https://%s.recruitee.com/api/offers/", lower);
        break;
    }
    default: return false;
    }
    return w > 0 && (size_t)w < n && (size_t)w <= JPF_MAX_URL_LEN;
}

void jpf_hex(const uint8_t *in, size_t n, char *out) {
    static const char h[] = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) { out[2 * i] = h[in[i] >> 4]; out[2 * i + 1] = h[in[i] & 15]; }
    out[2 * n] = 0;
}
