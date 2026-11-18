/* Unit tests for jp-searchd's index, filters, ranking, maps and request parsing. Run under ASan/UBSan. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "proto.h"
#include "sps.h"

static int failures = 0;
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); failures++; } } while (0)

static sps_doc doc(int64_t id, int rev, const char *title, const char *country, const char *mode, int posted, double smin, double smax,
                   const char *cur) {
    sps_doc d = {0};
    d.id = id; d.revision = rev;
    d.text[F_TITLE] = title; d.text[F_SKILLS] = "[\"Excel\", \"SAP\"]"; d.text[F_COMPANY] = "Acme"; d.text[F_LOCATION] = "";
    d.text[F_DESC] = "We are hiring for our finance team.";
    d.country = country; d.work_mode = mode; d.employment_type = "Full-time"; d.seniority = ""; d.source = "greenhouse";
    d.currency = cur; d.company_id = 7; d.posted_day = posted; d.sal_min = smin; d.sal_max = smax;
    return d;
}

static int64_t ids[64];
static size_t run(sps_index *ix, sps_query *q) {
    sps_result r;
    CHECK(sps_search(ix, q, 20000, &r));
    size_t n = r.n < 64 ? r.n : 64;
    for (size_t i = 0; i < n; i++) ids[i] = r.hits[i].id;
    sps_result_free(&r);
    return n;
}

static void tok(const char *t, size_t n, void *ud) { char *out = ud; strncat(out, t, n); strcat(out, "|"); }

static void test_tokenizer(void) {
    char out[256] = "";
    sps_tokenize("Senior C++ / C# Developer, and the R&D team", 43, 0, false, tok, out);
    CHECK(!strcmp(out, "senior|c++|c#|developer|r|d|team|"));
    out[0] = 0;
    sps_tokenize("a I x Bengaluru", 15, 0, true, tok, out);  /* description mode drops single letters */
    CHECK(!strcmp(out, "bengaluru|"));
}

static void test_search(void) {
    sps_index *ix = sps_index_new(NULL);
    sps_doc d[] = {
        doc(1, 1, "Accounts Receivable Analyst", "IN", "Hybrid", 19990, 800000, 1200000, "INR"),
        doc(2, 1, "Senior Accounts Receivable Specialist", "IN", "Remote", 19900, NAN, NAN, ""),
        doc(3, 1, "Software Engineer", "IN", "On-site", 19995, 2000000, 3000000, "INR"),
        doc(4, 1, "Accounts Receivable Analyst", "US", "Remote", 19998, 70000, 90000, "USD"),
    };
    d[1].remote_scope[0] = "IN"; d[1].n_remote = 1;
    d[3].remote_scope[0] = "US"; d[3].n_remote = 1;
    for (int i = 0; i < 4; i++) CHECK(sps_index_upsert(ix, &d[i]));
    CHECK(ix->nlive == 4);

    sps_query q = {.terms = {"accounts receivable"}, .nterms = 1, .posted_after_day = -1, .limit = 10};
    size_t n = run(ix, &q);
    CHECK(n == 3 && ids[0] != 3 && ids[1] != 3 && ids[2] != 3);  /* the engineer has neither word */
    /* exact filters: India, or remote open to India */
    q.ngroups = 1; q.groups[0][0] = "country:IN"; q.groups[0][1] = "remote:IN"; q.group_len[0] = 2;
    n = run(ix, &q);
    CHECK(n == 2);
    for (size_t i = 0; i < n; i++) CHECK(ids[i] == 1 || ids[i] == 2);
    /* AND across groups */
    q.ngroups = 2; q.groups[1][0] = "mode:Remote"; q.group_len[1] = 1;
    CHECK(run(ix, &q) == 1 && ids[0] == 2);
    /* an unknown filter value matches nothing (never "ignore the filter") */
    q.ngroups = 1; q.groups[0][0] = "country:ZZ"; q.group_len[0] = 1;
    CHECK(run(ix, &q) == 0);
    /* dates: unknown dates are excluded once a window is asked for */
    q.ngroups = 0; q.posted_after_day = 19950;
    n = run(ix, &q);
    CHECK(n == 2);
    for (size_t i = 0; i < n; i++) CHECK(ids[i] == 1 || ids[i] == 4);
    /* salary: same currency only, never converted; unknown only when allowed */
    q.posted_after_day = -1; q.salary_currency = "INR"; q.salary_min = 1000000;
    CHECK(run(ix, &q) == 1 && ids[0] == 1);
    q.salary_unknown_ok = true;
    n = run(ix, &q);
    CHECK(n == 2);
    q.salary_currency = NULL; q.salary_unknown_ok = false;
    /* all terms required */
    sps_query qa = {.terms = {"receivable", "senior"}, .nterms = 2, .posted_after_day = -1, .limit = 10, .require_all_terms = true};
    CHECK(run(ix, &qa) == 1 && ids[0] == 2);
    qa.terms[1] = "zzzunknown";
    CHECK(run(ix, &qa) == 0);
    /* no words: newest first */
    sps_query qn = {.posted_after_day = -1, .limit = 2};
    CHECK(run(ix, &qn) == 2 && ids[0] == 4 && ids[1] == 3);
    /* updates: same revision is a no-op; a newer one replaces; removal hides */
    CHECK(sps_index_upsert(ix, &d[0]) && ix->ndocs == 4);
    sps_doc d1 = doc(1, 2, "Collections Specialist", "IN", "Hybrid", 19990, NAN, NAN, "");
    CHECK(sps_index_upsert(ix, &d1) && ix->ndocs == 5 && ix->nlive == 4);
    sps_query qc = {.terms = {"collections"}, .nterms = 1, .posted_after_day = -1, .limit = 10};
    CHECK(run(ix, &qc) == 1 && ids[0] == 1);
    sps_query qr = {.terms = {"receivable"}, .nterms = 1, .posted_after_day = -1, .limit = 10};
    n = run(ix, &qr);
    CHECK(n == 2);
    for (size_t i = 0; i < n; i++) CHECK(ids[i] != 1);  /* the old text of posting 1 is gone */
    CHECK(sps_index_remove(ix, 4) && ix->nlive == 3);
    CHECK(run(ix, &qr) == 1 && ids[0] == 2);
    CHECK(sps_index_dead_ratio(ix) > 0.3);
    /* ties at the cut-off keep the lowest posting ids, even when a later update moved a posting to the end */
    sps_index *t = sps_index_new(NULL);
    for (int i = 10; i >= 1; i--) { sps_doc x = doc(i, 1, "Analyst", "IN", "Remote", 19000, NAN, NAN, ""); sps_index_upsert(t, &x); }
    sps_doc x2 = doc(2, 2, "Analyst", "IN", "Remote", 19000, NAN, NAN, "");
    sps_index_upsert(t, &x2);
    sps_query qt = {.posted_after_day = -1, .limit = 3};
    CHECK(run(t, &qt) == 3 && ids[0] == 1 && ids[1] == 2 && ids[2] == 3);
    sps_query qw = {.terms = {"analyst"}, .nterms = 1, .posted_after_day = -1, .limit = 3};
    CHECK(run(t, &qw) == 3 && ids[0] == 1 && ids[1] == 2 && ids[2] == 3);
    sps_index_free(t);
    sps_index_free(ix);
}

static void test_idmap(void) {
    sps_idmap m;
    sps_idmap_init(&m, 4);
    static int64_t ref[5000];
    for (int i = 0; i < 5000; i++) { ref[i] = (int64_t)i * 7919 - 100000; CHECK(sps_idmap_put(&m, ref[i], (uint32_t)i)); }
    for (int i = 0; i < 5000; i += 3) CHECK(sps_idmap_del(&m, ref[i]));
    for (int i = 0; i < 5000; i++) {
        uint32_t v;
        bool got = sps_idmap_get(&m, ref[i], &v);
        if (i % 3 == 0) CHECK(!got);
        else CHECK(got && v == (uint32_t)i);
    }
    CHECK(m.len == 5000 - 1667);
    sps_idmap_free(&m);
}

static void test_parse(void) {
    yyjson_doc *d;
    sps_query q;
    char err[160];
    const char *ok = "{\"method\":\"search\",\"terms\":[\"ar analyst\"],\"filters\":[[\"country:IN\",\"remote:IN\"]],\"posted_after_day\":19990,"
                     "\"salary\":{\"currency\":\"INR\",\"min\":500000,\"unknown_ok\":true},\"limit\":20,\"all_terms\":false}";
    CHECK(sps_parse_request(ok, strlen(ok), &d, &q, err, sizeof err) == REQ_SEARCH);
    CHECK(q.nterms == 1 && q.ngroups == 1 && q.group_len[0] == 2 && q.limit == 20 && q.salary_unknown_ok && q.posted_after_day == 19990);
    yyjson_doc_free(d);
    const char *bad[] = {"", "nope", "[]", "{\"method\":\"drop\"}", "{\"method\":\"search\",\"terms\":\"x\"}",
                         "{\"method\":\"search\",\"limit\":0}", "{\"method\":\"search\",\"limit\":999999}",
                         "{\"method\":\"search\",\"filters\":[[]]}", "{\"method\":\"search\",\"salary\":{\"currency\":\"RUPEE\",\"min\":1}}", NULL};
    for (int i = 0; bad[i]; i++) {
        CHECK(sps_parse_request(bad[i], strlen(bad[i]), &d, &q, err, sizeof err) == REQ_BAD && err[0]);
        yyjson_doc_free(d);
    }
    CHECK(sps_parse_request("{\"method\":\"health\"}", 19, &d, &q, err, sizeof err) == REQ_HEALTH);
    yyjson_doc_free(d);
}

static void test_title_candidates(void) {
    sps_index *ix = sps_index_new(NULL);
    sps_doc a = doc(1, 1, "FP&A Analyst", "IN", "Remote", 19000, NAN, NAN, "");
    sps_doc b = doc(2, 1, "Associate Director, Finance", "IN", "Remote", 19000, NAN, NAN, "");
    sps_doc c = doc(3, 1, "Développeur C++", "FR", "Remote", 19000, NAN, NAN, "");
    sps_doc e = doc(4, 1, "Accounts Receivable Specialist", "IN", "Remote", 19000, NAN, NAN, "");
    e.text[F_DESC] = "Work with our associate team";  /* "associate" only in the description: not a title match */
    sps_index_upsert(ix, &a); sps_index_upsert(ix, &b); sps_index_upsert(ix, &c); sps_index_upsert(ix, &e);
    sps_query q = {.terms = {"fp and a"}, .nterms = 1, .title_only = true, .posted_after_day = -1, .limit = 10};
    CHECK(run(ix, &q) == 1 && ids[0] == 1);                     /* "FP&A" normalised like JobPilot: fp and a */
    sps_query p = {.terms = {"associat"}, .nterms = 1, .title_only = true, .prefix = true, .posted_after_day = -1, .limit = 10};
    CHECK(run(ix, &p) == 1 && ids[0] == 2);                     /* prefix in titles only, never descriptions */
    p.prefix = false;
    CHECK(run(ix, &p) == 0);
    sps_query u = {.terms = {"d veloppeur"}, .nterms = 1, .title_only = true, .posted_after_day = -1, .limit = 10};
    CHECK(run(ix, &u) == 1 && ids[0] == 3);                     /* non-ASCII letters separate words, as in normalize_text */
    char words[10][SPS_MAX_TOKEN + 1];
    size_t n = sps_suggest(ix, "Ac", words, 10);
    CHECK(n == 1 && !strcmp(words[0], "accounts"));
    CHECK(sps_suggest(ix, "a", words, 10) == 0);                  /* at least two letters */
    sps_index_free(ix);
}

int main(void) {
    test_title_candidates();
    test_tokenizer();
    test_search();
    test_idmap();
    test_parse();
    if (failures) { fprintf(stderr, "%d check(s) failed\n", failures); return 1; }
    puts("all searchd core tests passed");
    return 0;
}
