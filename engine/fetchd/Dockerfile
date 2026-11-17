# jp-fetchd: build, test under sanitizers, fuzz briefly, then ship a small non-root image.
FROM debian:trixie-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc clang libclang-rt-19-dev cmake make pkg-config libc6-dev \
      libcurl4-openssl-dev libpq-dev libyyjson-dev libxxhash-dev ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY CMakeLists.txt ./
COPY src ./src
COPY tests ./tests
COPY fuzz ./fuzz
# 1. tests under AddressSanitizer + UndefinedBehaviorSanitizer
RUN cmake -S . -B /san -DJPF_SANITIZE=ON -DCMAKE_BUILD_TYPE=Debug && cmake --build /san -j && ctest --test-dir /san --output-on-failure
# 2. a short libFuzzer run over the splitter and hash map (the nightly run is longer)
ARG FUZZ_SECONDS=30
RUN clang -std=c17 -g -O1 -fsanitize=fuzzer,address,undefined -Isrc $(pkg-config --cflags yyjson libxxhash) \
      fuzz/fuzz_split.c src/split.c src/hashmap.c src/policy.c $(pkg-config --libs yyjson libxxhash) -o /fuzz_split && \
    mkdir -p /corpus && printf '\000{"jobs":[{"id":1}]}' > /corpus/gh && printf '\001[{"id":"a"}]' > /corpus/lever && \
    /fuzz_split -max_total_time=${FUZZ_SECONDS} -max_len=65536 /corpus
# 3. the release build
RUN cmake -S . -B /rel -DCMAKE_BUILD_TYPE=Release && cmake --build /rel -j && strip /rel/jp-fetchd

FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends libcurl4t64 libpq5 libyyjson0 libxxhash0 ca-certificates \
    && rm -rf /var/lib/apt/lists/* && useradd --system --uid 10002 --no-create-home jpf
COPY --from=build /rel/jp-fetchd /usr/local/bin/jp-fetchd
USER 10002
ENTRYPOINT ["/usr/local/bin/jp-fetchd"]
