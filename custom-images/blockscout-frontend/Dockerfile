# Rebuild of the upstream GPL-3.0 image with its end-of-life Alpine 3.20
# packages upgraded to a maintained Alpine release. Application files are
# unchanged. Upstream source: https://github.com/blockscout/frontend/tree/v1.38.2
FROM ghcr.io/blockscout/frontend:v1.38.2@sha256:0b5e29149b3f7cd1f988458b46543c49f17a0a0ebb108c85a7cbb315f7907adf

LABEL org.opencontainers.image.title="Blockscout frontend v1.38.2" \
      org.opencontainers.image.source="https://github.com/DogeOS69/scroll-sdk" \
      org.opencontainers.image.base.name="ghcr.io/blockscout/frontend:v1.38.2" \
      org.opencontainers.image.licenses="GPL-3.0" \
      org.opencontainers.image.description="Blockscout frontend v1.38.2 rebuilt on Alpine 3.24 packages; upstream source https://github.com/blockscout/frontend/tree/v1.38.2"

USER root
RUN sed -i 's#/alpine/v3\.20/#/alpine/v3.24/#' /etc/apk/repositories \
 && apk upgrade --no-cache --available \
 && apk add --no-cache --upgrade alpine-release \
 && for f in alpine-release os-release issue; do \
      if [ -e "/etc/$f.apk-new" ]; then mv -f "/etc/$f.apk-new" "/etc/$f"; fi; \
    done \
 && rm -rf /var/cache/apk/*
USER nextjs
