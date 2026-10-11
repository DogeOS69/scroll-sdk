# Build context: clean dogeos-core checkout at CORE_REVISION, not this SDK.
# No proof/circuit feature is changed; this packages the existing Core binary.
FROM dogeos69/rust-chef:nightly-2026-03-17-bookworm AS builder
WORKDIR /app
COPY . .
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/usr/local/cargo/git \
    cargo build --locked --release -p proof_coordinator --bin capacity-manager
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates libsqlite3-0 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/capacity-manager /usr/local/bin/capacity-manager
ARG CORE_REVISION
LABEL org.opencontainers.image.source="https://github.com/DogeOS69/dogeos-core" \
      org.opencontainers.image.revision="${CORE_REVISION}" \
      org.opencontainers.image.title="capacity-manager"
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/capacity-manager"]
