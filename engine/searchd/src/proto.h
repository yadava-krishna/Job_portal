#ifndef SPS_PROTO_H
#define SPS_PROTO_H
#include <yyjson.h>
#include "sps.h"
enum { REQ_BAD = -1, REQ_SEARCH = 1, REQ_HEALTH = 2, REQ_STATS = 3 };
int sps_parse_request(const char *buf, size_t len, yyjson_doc **doc_out, sps_query *q, char *err, size_t n);
#endif
