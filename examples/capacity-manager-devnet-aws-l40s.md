# DevNet AWS L40S candidate: disabled pending qualification

`values/capacity-manager-devnet-aws-l40s.yaml` is a candidate for the AWS-primary
Capacity Manager path. It deliberately sets `prepared: false`, so installation
fails closed. It is not an enabled default or a second allocator. The isolated
L40S test is bounded by the existing USD 10 compute budget. For this DevNet
rollout, the operator authorized an ongoing GPU ceiling of USD 3.10/hour
conditional on performance qualification. That authorization is separate from
the lab budget and does not remove the remaining activation gates.

## Placement and external prerequisites

Before explicitly enabling this profile, confirm the approved USD 3.10/hour
ceiling and provision/offer-only validate the dedicated dstack fleet
`devnet-provers-aws/devnet-capacity-manager-active-aws-l40s`:

- AWS, `us-east-1`, on-demand `g6e.4xlarge`, nodes 0..1;
- exactly one L40S, nominal 48GB VRAM, at least 44GiB usable;
- minimum 16 CPUs, 128GiB RAM and 200GiB disk;
- hourly instance price at or below USD 3.10 and a bounded idle policy.

The chart creates neither provider configuration nor fleet. Check actual
offer resources, availability and price rather than assuming the instance name
guarantees them; include storage/traffic in budgeting. Verify provider VPC/subnet
coverage for the selected GPU instance type: the initial isolated test found
`InsufficientInstanceCapacity` in `us-east-1a` and `Unsupported` in `us-east-1f`,
while AWS suggested `us-east-1b`, `us-east-1c` or `us-east-1d`. Both errors were
reported by dstack as `NoCapacityError`. A priced regional offer alone does not
validate supported availability zones or live capacity. Preserve bounded retry
and manual fallback rather than retrying an unsupported placement indefinitely. AWS credentials remain
inside the existing dstack controller/provider path. The manager has no AWS
credentials, IRSA annotation or Kubernetes API token.

Reuse the existing `devnet-capacity-manager-active` release, worker prefix and
unannotated ServiceAccount, external `devnet-capacity-manager-active-state` PVC,
WP Secret `devnet-capacity-manager-active-wp-token`/`proof-work-token` and dstack
Secret `dstack-controller-auth`/`admin-token` in `dstack-system`. Prepare and
verify project Secret `cm_active_worker_token_1013` in `devnet-provers-aws`;
same-named secrets in another project do not supply worker auth here. Never put
credential values in this profile or overwrite unrelated auth.

Follow the single-owner handoff in `capacity-manager-devnet-aws.md`. Drain using
the original provider configuration, confirm zero leases, terminal tasks,
manager shutdown and actual provider instance/disk cleanup before replacing
capacity. Preserve the PVC and checkpoints. Project and worker prefix determine
the state-file identity; different worker image/architecture/fleet selectors
change the ownership fingerprint. Do not erase state or start a second manager
to bypass mismatched live ownership. The SDK task remains retired and its old
watchdog suspended.

## Truthful architecture and proof contract

The manager image stays pinned to the existing qualified digest. The worker
image changes to
`dogeos69/prover-worker-cuda@sha256:5f170b2150877b66ce8c3daa1c467d8ac60947c1f229f913cab1247e79efb2b9`,
built for CUDA architecture 89 from source
`350508c1cd068230fc731747a3b5bbfbb44b81cf`. This is a different binary/source
contract from the original 5c beta worker. The newer develop lineage includes
host deadline/drain changes associated with Core PRs #1468/#1469. Source review
found no difference in successful-proof logic, guest/programs, canonical API or
dependency pins; different binary and toolchain remain comparison confounds.

The worker command differs from the RTX3090/A10G command only in the shell
compute-capability check, from 86 to 89. Its SHA256 is
`8e4fd7192a23915c62eaef8e8e7438ed9b0fc568678d7c4019fecbeec78d0f97`.
All program hashes, protocol/genesis context, artifact paths, proving-family
roles, parallelism and drain settings are preserved. The image's declared
compiled architecture and runtime startup check agree; no CUDA guard is
disabled or bypassed. All family VRAM minima remain 16GiB.

The isolated L40S exact-input replay produced a **valid proof in 206.947
seconds**, compared with 253.489 seconds for the historical SDK and 218.352
seconds for the qualified CM RTX3090 placement: 18.4% and 5.2% faster,
respectively. Total request time was 217.783 seconds; STARK proving was 208.023
seconds. Cycles, public inputs, program, canonical verification key, actual
image/binary identity and full child completion were validated. Cold preparation
ran before the timed proof; its duration was not exported in the sanitized
receipt and is not included in this comparison. These are single samples with
different hosts/builds, not a throughput or GPU-only causality claim.

Allocation succeeded in `us-east-1d` after temporarily selecting an existing
supported VPC for the isolated AWS project. The original configuration is
preserved for restoration and the test rental must be removed afterward. This
placement is qualification evidence, not a production network recommendation.
The lab used synthetic capacity and offline proof replay without production
coordinator claims or WP/PC production auth. A valid chunk replay does not
establish all-family production readiness or launch throughput. Those gates
remain outstanding, so `prepared: false` is retained. The ongoing USD 3.10/hour
ceiling is authorized conditional on performance qualification.
The chunk policy estimate is 240 seconds based on this 206.947-second sample;
all estimates remain provisional pending production workload distributions.

## Explicit activation gate

Do not set `prepared: true` merely to bypass the install error. Before a live
activation, verify the approved ongoing ceiling, external fleet/auth/state,
validated current-image proof results and all-family real-mode acceptance.
Render and review the same-release handoff first; retain enough native shutdown
grace and actual cleanup evidence. Once explicitly approved/prepared, enable
only this profile for the existing release and verify the new exact provider
RunID's real-mode readiness, actual single GPU/price, queue ages and accepted
results. Historical readiness from another image or RunID is insufficient.

For static inspection only, with no provider or Kubernetes mutation:

```bash
helm template devnet-capacity-manager-active ../charts/capacity-manager \
  --namespace dstack-system \
  -f values/capacity-manager-devnet-aws-l40s.yaml --set prepared=true
```

The current Core path selects one provider/project per manager. These profiles
do not provide automatic failover; qualified Vast RTX3090 remains a manual
fallback when approved AWS capacity is unavailable or overpriced. Apply the
same drain-confirmed handoff when returning to a fallback, preserving CM
allocation ownership.
