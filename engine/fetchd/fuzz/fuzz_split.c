/* libFuzzer target: every ATS shape over arbitrary bytes. Build: clang -fsanitize=fuzzer,address,undefined */
#include <stdint.h>
#include <stdlib.h>
#include "../src/jpf.h"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 1) return 0;
    jpf_ats ats = (jpf_ats)(data[0] % ATS_UNKNOWN);
    jpf_board b;
    jpf_board_init(&b);
    jpf_split(ats, (const char *)data + 1, size - 1, &b);
    jpf_map m;
    jpf_map_init(&m, b.len);
    for (size_t i = 0; i < b.len; i++) jpf_map_put(&m, b.items[i].id, b.items[i].hash);
    for (size_t i = 0; i < b.len; i++) if (!jpf_map_get(&m, b.items[i].id)) abort();
    jpf_map_free(&m);
    jpf_board_free(&b);
    return 0;
}
