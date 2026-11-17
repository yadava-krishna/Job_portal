# jp-searchd: build, test under sanitizers, fuzz the request parser briefly, then ship a small non-root image.
FROM debian:trixie-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc clang libclang-rt-19-dev cmake make pkg-config libc6-dev \
      libpq-dev libyyjson-dev libxxhash-dev libroaring-dev ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt ./
COPY src ./src
COPY tests ./tests
COPY fuzz ./fuzz
RUN cmake -S . -B /san -DSPS_SANITIZE=ON -DCMAKE_BUILD_TYPE=Debug && cmake --build /san -j && ctest --test-dir /san --output-on-failure
ARG FUZZ_SECONDS=30
RUN clang -std=c17 -g -O1 -fsanitize=fuzzer,address,undefined -Isrc $(pkg-config --cflags yyjson libxxhash) \
      fuzz/fuzz_request.c src/text.c src/dict.c src/index.c src/proto.c -lroaring $(pkg-config --libs yyjson libxxhash) -lm -o /fuzz_request && \
    mkdir -p /corpus && printf '{"method":"search","terms":["ar analyst"],"filters":[["country:IN"]],"limit":5}' > /corpus/a && \
    /fuzz_request -max_total_time=${FUZZ_SECONDS} -max_len=8192 /corpus
RUN cmake -S . -B /rel -DCMAKE_BUILD_TYPE=Release && cmake --build /rel -j && strip /rel/jp-searchd

FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 libyyjson0 libxxhash0 libroaring0t64 \
    && rm -rf /var/lib/apt/lists/* && useradd --system --uid 10003 --no-create-home jps \
    && mkdir -p /run/jpse && chown 10003:10003 /run/jpse && chmod 755 /run/jpse  # seeds the shared socket volume
COPY --from=build /rel/jp-searchd /usr/local/bin/jp-searchd
USER 10003
ENTRYPOINT ["/usr/local/bin/jp-searchd"]
