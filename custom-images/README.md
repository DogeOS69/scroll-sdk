# Custom images

| Directory | Image | Release tag |
| --- | --- | --- |
| `l1-devnet` | `l1-devnet` | `l1-devnet-<version>` |
| `blockscout-scroll` | `ghcr.io/dogeos69/blockscout-scroll` | `blockscout-scroll-<version>` |
| `blockscout-frontend` | `ghcr.io/dogeos69/blockscout-frontend` | `blockscout-frontend-<version>` |

Pushing a release tag builds the image with `<version>` as the image tag.
`l1-devnet` is published to Docker Hub under the `DOCKERHUB_USERNAME`
account and also updates `latest`. The Blockscout images
are published to GitHub Container Registry with the workflow's `GITHUB_TOKEN`
and are linked to this public repository through the image source label, so
they can be pulled without credentials.

## Blockscout rebuilds

`blockscout-scroll` starts from the upstream GPL-3.0 image, pinned by digest,
and upgrades its end-of-life Alpine 3.20 packages to Alpine 3.24. It does not
change the application. The corresponding source is the upstream release named
in its Dockerfile plus the Dockerfile itself. Use a version suffix that names the
base, for example `blockscout-scroll-8.0.2-alpine3.24.1`.

`blockscout-frontend` is built from upstream source. `upstream.env` pins the
upstream repository and commit; the release workflow checks it out, applies
`v1.38.2.patch` and builds with the upstream Dockerfile. The corresponding
source is that upstream commit plus the patch. Modified on 2026-11-09 by DogeOS:

- Next.js 15.2.3 → 15.5.29 and `@next/bundle-analyzer` 15.5.29; the lockfile
  update also moves `sharp` to 0.35.5.
- Node.js 22.11.0 → 22.23.4 on Alpine 3.24 for every build stage, with the
  `engines` field updated to match.
- `pages/api/proxy.ts`: backport of the upstream v2.6.0 change that returns 404
  unless the deployment needs the Next.js API proxy.

Use a version suffix that identifies the patch revision, for example
`blockscout-frontend-v1.38.2-dogeos.1`.

Publishing an image does not change the Blockscout chart. Switch its image
repository and tag in a separate change after the image is available.
