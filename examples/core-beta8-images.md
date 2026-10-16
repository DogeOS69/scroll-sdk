# Core beta.8 image selection

New-deployment examples select Core `v0.3.0-beta.8`, source commit
`a0bc76bbdc85e1600c257768c417f2ea14981957`. Runtime and helper tags were checked
against the registry on 2026-10-17. The [tag image workflow](https://github.com/DogeOS69/dogeos-core/actions/runs/38946710224)
completed successfully, including the proof producer, CUDA worker and release.

## Runtime and helper images

Service values select `dogeos69/<service>:v0.3.0-beta.8` for
withdrawal-processor, l1-interface, tso-service, proof-coordinator,
eager-materializer, eth-da-submitter, fee-oracle and cubesigner-signer.

The spec pins the multi-platform bridge-genesis-tools image to
`dogeos69/bridge-genesis-tools@sha256:0d2d28be08cd44505a07fa822aa3f73ee00bde1fdac363ffc8891ec4a0160da8`.

The partner kit pins
`dogeos69/attestation-signer@sha256:0795b7d7a0fcec5a85170147753cae6c2ba7c5217b68289360cd8e249553a8e5`.
Its allowed binary identity is release version `0.3.0`, Git commit
`a0bc76bbdc85e1600c257768c417f2ea14981957`, signing policy version `1`.
The release version is the Cargo package version, not the image tag. Update
the image and all identity pins together. Existing signer identity files are
not automatically rewritten by updating the public kit templates.

## Published proof release and deployment compatibility

The spec selects `preparation.proofRelease.version: v0.3.0-beta.8`.
The [official proof release](https://github.com/DogeOS69/dogeos-core/releases/tag/proof-release-v0.3.0-beta.8)
was published on 2026-10-16 with `dogeos-proof-release-v1.json` and its checksum.
The verified manifest SHA-256 is
`9025c3b941e356b30552d08149dee5601fcbd11e3e3e0782ba35ce47e184d182`.
It pins the coordinator, topology compiler, bundle publisher, proof preparation
producer and CUDA worker to the same Core revision. Operators select the
version; the CLI downloads and checks these published assets.

Beta.8 changes bridge guest identity and worker authentication. Prepare and
validate matching proof materials; do not reuse beta.7 commitments merely
because the service tags have changed. Per-worker credentials require the
corresponding CLI/compiler and SDK integration, tracked in
[CLI #106](https://github.com/DogeOS69/scroll-sdk-cli/pull/106) and
[SDK #180](https://github.com/DogeOS69/scroll-sdk/pull/180). In particular, a
production worker compiler input needs `prover_worker.worker_credential_file`
separate from the proof-work token. Both PRs were still open when these pins
were updated. Selecting this release does not complete that integration or
establish a working proof deployment. Capacity-manager and recorded devnet GPU
profiles retain their independent pins until that integration is ready.

Policy compiler selections and CubeSigner governance approvals also remain
separate deployment inputs; use the matching reviewed compiler identity.
This image update does not publish or attach a policy or upgrade a live bridge.

Contracts use the matching `gen-configs-`, `deploy-` and `verify-` variants of
`dogeos-v0.3.0-rc.9`. Reth, preinstalls and frontends have their own release
versions. Historical release notes and deployment profiles are retained.
Chart defaults and chart versions are unchanged.
