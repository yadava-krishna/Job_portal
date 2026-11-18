/* Unit tests for the parts of jp-fetchd that see untrusted input: splitting, hashing, policy. Run under ASan/UBSan. */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "jpf.h"

static int failures = 0;
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static long split_str(jpf_ats a, const char *s, jpf_board *b) { return jpf_split(a, s, strlen(s), b); }

static void test_shapes(void) {
    jpf_board b;
    jpf_board_init(&b);
    CHECK(split_str(ATS_GREENHOUSE, "{\"jobs\":[{\"id\":101,\"title\":\"A\"},{\"id\":102,\"title\":\"B\"}],\"meta\":{}}", &b) == 2);
    CHECK(!strcmp(b.items[0].id, "101") && !strcmp(b.items[1].id, "102"));
    CHECK(strstr(b.items[0].json, "\"title\":\"A\"") != NULL);
    jpf_board_free(&b);

    jpf_board_init(&b);
    CHECK(split_str(ATS_LEVER, "[{\"id\":\"aaaa-1111\",\"text\":\"X\"},{\"id\":\"\"},{\"text\":\"no id\"},{\"id\":null}]", &b) == 1);
    CHECK(!strcmp(b.items[0].id, "aaaa-1111"));  /* empty, missing and null ids are dropped like parse_job drops them */
    jpf_board_free(&b);

    jpf_board_init(&b);
    CHECK(split_str(ATS_ASHBY, "{\"jobs\":[{\"id\":\"u1\"},{\"id\":\"u1\"},{\"id\":0},{\"id\":-5}]}", &b) == 2);
    CHECK(!strcmp(b.items[1].id, "-5"));  /* duplicate u1 kept once; 0 is falsy; negative ints are ids */
    jpf_board_free(&b);

    jpf_board_init(&b);
    CHECK(split_str(ATS_SMARTRECRUITERS, "{\"offset\":0,\"limit\":100,\"totalFound\":250,\"content\":[{\"id\":\"744\"},{\"id\":\"744\"},{\"x\":1}]}", &b) == 1);
    CHECK(b.total_found == 250 && b.last_page_len == 3);  /* paging looks at the page's items, not the new ones */
    jpf_board_free(&b);

    jpf_board_init(&b);
    CHECK(split_str(ATS_RECRUITEE, "{\"offers\":[{\"id\":7,\"title\":\"T\",\"status\":\"published\"}]}", &b) == 1);
    jpf_board_free(&b);

    const char *bad[] = {"", "<html>oops</html>", "{\"unexpected\":true}", "{\"jobs\":{}}", "[1,2", "null", "\"jobs\"", NULL};
    for (int i = 0; bad[i]; i++) {
        jpf_board_init(&b);
        CHECK(split_str(ATS_GREENHOUSE, bad[i], &b) == -1 && b.error[0]);
        jpf_board_free(&b);
    }
    jpf_board_init(&b);
    CHECK(split_str(ATS_LEVER, "{\"jobs\":[]}", &b) == -1);  /* Lever answers with a bare array */
    jpf_board_free(&b);
}

static void test_hash_is_content_based(void) {
    jpf_board a, b;
    jpf_board_init(&a);
    jpf_board_init(&b);
    split_str(ATS_GREENHOUSE, "{\"jobs\":[{\"id\":1,\"title\":\"A\"}]}", &a);
    split_str(ATS_GREENHOUSE, "{ \"jobs\" : [ { \"id\" : 1 , \"title\" : \"A\" } ] }", &b);  /* whitespace only */
    CHECK(!memcmp(a.items[0].hash, b.items[0].hash, 16));
    jpf_board_free(&b);
    jpf_board_init(&b);
    split_str(ATS_GREENHOUSE, "{\"jobs\":[{\"id\":1,\"title\":\"B\"}]}", &b);
    CHECK(memcmp(a.items[0].hash, b.items[0].hash, 16) != 0);
    jpf_board_free(&a);
    jpf_board_free(&b);
}

static void test_map(void) {
    jpf_map m;
    jpf_map_init(&m, 4);
    uint8_t v[16];
    char k[32];
    for (int i = 0; i < 5000; i++) {  /* forces several resizes */
        memset(v, i & 0xff, 16);
        snprintf(k, sizeof k, "id-%d", i);
        CHECK(jpf_map_put(&m, k, v));
    }
    CHECK(m.len == 5000);
    for (int i = 0; i < 5000; i += 97) {
        snprintf(k, sizeof k, "id-%d", i);
        const uint8_t *got = jpf_map_get(&m, k);
        CHECK(got && got[0] == (uint8_t)(i & 0xff));
    }
    CHECK(jpf_map_get(&m, "missing") == NULL);
    memset(v, 9, 16);
    CHECK(jpf_map_put(&m, "id-1", v) && m.len == 5000 && jpf_map_get(&m, "id-1")[0] == 9);  /* overwrite, no growth */
    jpf_map_free(&m);
}

static void test_policy(void) {
    CHECK(jpf_token_ok("acmefintech") && jpf_token_ok("Bosch.Group_1-x"));
    CHECK(!jpf_token_ok("") && !jpf_token_ok("-x") && !jpf_token_ok("a/b") && !jpf_token_ok("a..b") && !jpf_token_ok("a b"));
    CHECK(jpf_host_allowed("boards-api.greenhouse.io") && jpf_host_allowed("api.eu.lever.co") && jpf_host_allowed("epsilonpay.recruitee.com"));
    CHECK(!jpf_host_allowed("evil.com") && !jpf_host_allowed("a.b.recruitee.com") && !jpf_host_allowed("greenhouse.io.evil.com"));
    CHECK(jpf_host_denied("www.linkedin.com") && jpf_host_denied("naukri.com") && jpf_host_denied("in.indeed.com") &&
          jpf_host_denied("www.glassdoor.co.in") && !jpf_host_denied("notlinkedin.com"));
    struct sockaddr_in v4 = {.sin_family = AF_INET};
    const char *bad4[] = {"127.0.0.1", "10.1.2.3", "172.20.0.4", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0", "224.0.0.1", NULL};
    for (int i = 0; bad4[i]; i++) { inet_pton(AF_INET, bad4[i], &v4.sin_addr); CHECK(jpf_ip_forbidden((struct sockaddr *)&v4, false)); }
    inet_pton(AF_INET, "104.18.12.33", &v4.sin_addr);
    CHECK(!jpf_ip_forbidden((struct sockaddr *)&v4, false));
    inet_pton(AF_INET, "127.0.0.1", &v4.sin_addr);
    CHECK(!jpf_ip_forbidden((struct sockaddr *)&v4, true));  /* test mode only */
    struct sockaddr_in6 v6 = {.sin6_family = AF_INET6};
    const char *bad6[] = {"::1", "fe80::1", "fd00::1", "::ffff:10.0.0.1", "::", NULL};
    for (int i = 0; bad6[i]; i++) { inet_pton(AF_INET6, bad6[i], &v6.sin6_addr); CHECK(jpf_ip_forbidden((struct sockaddr *)&v6, false)); }
    const char *bad6b[] = {"64:ff9b::a00:1", "64:ff9b:1::1", "2002:a00:1::1", "2001::1", "100::1", "::ffff:0:a00:1", NULL};
    for (int i = 0; bad6b[i]; i++) { inet_pton(AF_INET6, bad6b[i], &v6.sin6_addr); CHECK(jpf_ip_forbidden((struct sockaddr *)&v6, false)); }
    inet_pton(AF_INET, "198.19.1.1", &v4.sin_addr);
    CHECK(jpf_ip_forbidden((struct sockaddr *)&v4, false));
    inet_pton(AF_INET6, "2606:4700::6810:e684", &v6.sin6_addr);
    CHECK(!jpf_ip_forbidden((struct sockaddr *)&v6, false));
}

static void test_urls(void) {  /* must equal the Python clients' URLs (backend/services/ats/*.py) */
    char u[700];
    CHECK(jpf_board_url(ATS_GREENHOUSE, "acmefintech", "", 0, u, sizeof u) && !strcmp(u, "https://boards-api.greenhouse.io/v1/boards/acmefintech/jobs?content=true"));
    CHECK(jpf_board_url(ATS_LEVER, "betapay", "eu", 0, u, sizeof u) && !strcmp(u, "https://api.eu.lever.co/v0/postings/betapay?mode=json"));
    CHECK(jpf_board_url(ATS_ASHBY, "gammaco", "", 0, u, sizeof u) && !strcmp(u, "https://api.ashbyhq.com/posting-api/job-board/gammaco?includeCompensation=true"));
    CHECK(jpf_board_url(ATS_SMARTRECRUITERS, "BoschGroup", "IN", 100, u, sizeof u) &&
          !strcmp(u, "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings?limit=100&offset=100&country=in"));
    CHECK(jpf_board_url(ATS_RECRUITEE, "EpsilonPay", "", 0, u, sizeof u) && !strcmp(u, "https://epsilonpay.recruitee.com/api/offers/"));
    CHECK(!jpf_board_url(ATS_RECRUITEE, "a.b", "", 0, u, sizeof u));
    CHECK(!jpf_board_url(ATS_GREENHOUSE, "../etc", "", 0, u, sizeof u));
}

int main(void) {
    test_shapes();
    test_hash_is_content_based();
    test_map();
    test_policy();
    test_urls();
    if (failures) { fprintf(stderr, "%d check(s) failed\n", failures); return 1; }
    puts("all core tests passed");
    return 0;
}
