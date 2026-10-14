# Core beta.7 image selection

The new-deployment examples select Core `v0.3.0-beta.7`, source commit
`50653e7b67e2a6a8eadef06fabdec8037e6f61ef`. This is an image-selection update,
not an instruction to upgrade a running bridge or reuse old proof material.

## Published runtime and helper images

The service values select `dogeos69/<service>:v0.3.0-beta.7` for
withdrawal-processor, l1-interface, tso-service, proof-coordinator,
eager-materializer, eth-da-submitter, fee-oracle and cubesigner-signer.
The standard WP release includes sequencer KMS support; new deployments no
longer need the separate beta.6-kms tag. The fee wallet remains separately
configured.

The spec pins the multi-platform bridge-genesis-tools image to
`dogeos69/bridge-genesis-tools@sha256:d165e828ae53f9a4af5bc60d7ed9244176b3db2307f567eedb4d7f3c01db6339`.
This release includes the Core #1573 Bridge funding marker fix.

The partner kit pins
`dogeos69/attestation-signer@sha256:7727d3c8dbf2f59f6e48993d1a6885707d4dadfe177cbaf9e3c2ee9986e2d7a0`.
Its allowed binary identity is release version `0.3.0`, Git commit
`50653e7b67e2a6a8eadef06fabdec8037e6f61ef`, signing policy version `1`.
The binary release version is the Cargo package version, not the image tag.
Update the image and allowed identity together. The release includes the native
`inspect-rotation` command.

## Proof release and policy compiler prerequisites

The spec requests `preparation.proofRelease.version: v0.3.0-beta.7`.
The CLI requires the separate GitHub release `proof-release-v0.3.0-beta.7`,
including `dogeos-proof-release-v1.json` and its published checksum. It obtains
the producer, CUDA worker and other proof-image digests from that manifest;
service tags alone cannot replace it.

At verification on 2026-10-15, the service images and helper/signer digests were
published, but the [tag image workflow](https://github.com/DogeOS69/dogeos-core/actions/runs/38591710770)
was still running and the proof release was not yet available. Planning remains
blocked until those assets are published. Do not fall back to beta.6 proofexp
or fabricate release digests. beta.7 includes updated proving programs: bake and
validate the matching deployment materials before claiming end-to-end readiness.

The [policy compiler workflow](https://github.com/DogeOS69/dogeos-core/actions/runs/38591710274)
succeeded. Where policy compilation is selected, use the reviewed beta.7 compiler
from private `ghcr.io/dogeos69/cubesigner-policy-compiler`, pinned by its actual
digest and the Core revision above. This PR does not invent that digest, publish
or attach a policy, or change Council approval requirements.

Contracts rc.6, Reth, frontends, dstack and capacity-manager have independent
release selections and are not bumped by this update. Historical deployment
profiles and beta.6 incident/rollout records are retained as historical evidence.
Chart defaults and chart versions are unchanged.
