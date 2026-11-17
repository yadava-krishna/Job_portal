#ifndef SPS_SYNC_H
#define SPS_SYNC_H
#include <libpq-fe.h>
#include "server.h"
int64_t sps_outbox_max(PGconn *c);
sps_index *sps_build(PGconn *c, const double *avg, char *err, size_t n);
long sps_refresh(PGconn *c, sps_state *st, sps_idmap *seen, char *err, size_t n);
bool sps_rebuild(PGconn *c, sps_state *st, sps_idmap *seen, const double *avg, char *err, size_t n);
#endif
