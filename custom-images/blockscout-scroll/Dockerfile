# Rebuild of the upstream GPL-3.0 image with its end-of-life Alpine 3.20
# packages upgraded to a maintained Alpine release. Application files are
# unchanged. Upstream source: https://github.com/blockscout/blockscout/tree/v8.0.2
FROM ghcr.io/blockscout/blockscout-scroll:8.0.2@sha256:735cd83a36acfeda287ebaa539da05d2ec52b66c7e5474ab7365906916337c4e

LABEL org.opencontainers.image.title="Blockscout 8.0.2 (scroll)" \
      org.opencontainers.image.source="https://github.com/DogeOS69/scroll-sdk" \
      org.opencontainers.image.base.name="ghcr.io/blockscout/blockscout-scroll:8.0.2" \
      org.opencontainers.image.licenses="GPL-3.0" \
      org.opencontainers.image.description="Blockscout 8.0.2 (scroll) rebuilt on Alpine 3.24 packages; upstream source https://github.com/blockscout/blockscout/tree/v8.0.2"

USER root
RUN sed -i 's#/alpine/v3\.20/#/alpine/v3.24/#' /etc/apk/repositories \
 && apk upgrade --no-cache --available \
 && apk add --no-cache --upgrade alpine-release \
 && for f in alpine-release os-release issue; do \
      if [ -e "/etc/$f.apk-new" ]; then mv -f "/etc/$f.apk-new" "/etc/$f"; fi; \
    done \
 && rm -rf /var/cache/apk/*
USER blockscout:blockscout
