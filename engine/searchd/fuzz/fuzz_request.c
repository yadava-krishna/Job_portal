/* libFuzzer: arbitrary request frames through the parser and, when valid, a search on a small index. */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include "../src/proto.h"

static sps_index *ix;

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (!ix) {
        ix = sps_index_new(NULL);
        sps_doc d = {.id = 1, .revision = 1, .text = {"Accounts Receivable Analyst", "[\"Excel\"]", "Acme", "Pune", "desc"},
                     .country = "IN", .work_mode = "Remote", .employment_type = "", .seniority = "", .source = "lever",
                     .currency = "INR", .posted_day = 19000, .sal_min = 1, .sal_max = NAN};
        sps_index_upsert(ix, &d);
    }
    yyjson_doc *doc;
    sps_query q;
    char err[160];
    if (sps_parse_request((const char *)data, size, &doc, &q, err, sizeof err) == REQ_SEARCH) {
        sps_result r;
        if (sps_search(ix, &q, 20000, &r)) sps_result_free(&r);
    }
    yyjson_doc_free(doc);
    return 0;
}
