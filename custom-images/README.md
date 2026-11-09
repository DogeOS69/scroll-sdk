# Custom images

| Directory | Image | Release tag |
| --- | --- | --- |
| `l1-devnet` | `l1-devnet` | `l1-devnet-<version>` |
| `blockscout-scroll` | `ghcr.io/dogeos69/blockscout-scroll` | `blockscout-scroll-<version>` |
| `blockscout-frontend` | `ghcr.io/dogeos69/blockscout-frontend` | `blockscout-frontend-<version>` |

Pushing a release tag builds the image with `<version>` as the image tag.
`l1-devnet` is published to Docker Hub under the `DOCKERHUB_USERNAME`
account and also updates `latest`. The Blockscout images
are published to GitHub Container Registry with the workflow's `GITHUB_TOKEN`.
A new GHCR package is private: after its first release, an organization
administrator must set it to public and link it to this repository.

## Blockscout rebuilds

`blockscout-scroll` and `blockscout-frontend` start from the upstream GPL-3.0
images, pinned by digest, and upgrade their end-of-life Alpine 3.20 packages
to Alpine 3.24. They do not change the application. The corresponding source
is the upstream release named in each Dockerfile plus the Dockerfile itself.

Application dependencies bundled by upstream, such as the frontend's npm
packages, are unchanged; fixing them requires rebuilding from source. Use a
version suffix that names the base, for example
`blockscout-scroll-8.0.2-alpine3.24.1`.

Publishing an image does not change the Blockscout chart. Switch its image
repository and tag in a separate change after the image is available.
