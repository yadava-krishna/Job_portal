#ifndef SPS_SERVER_H
#define SPS_SERVER_H
#include <pthread.h>
#include "sps.h"
typedef struct {
    pthread_rwlock_t lock;
    sps_index *ix;          /* swapped under the write lock on a full rebuild */
    double last_sync;       /* monotonic time of the last successful sync */
    int64_t high_water;     /* highest index_outbox id seen */
    unsigned rebuilds;
} sps_state;
int sps_serve(sps_state *st, const char *path, volatile int *stop);
#endif
