# DevNet Capacity Manager: AWS primary with manual Vast fallback

Use `values/capacity-manager-devnet-aws-a10g.yaml` as the **primary AWS path for
all four proving families**, in namespace `dstack-system`. Vast RTX3090 is the
fallback when AWS capacity is unavailable or its price exceeds the configured
ceiling. Both profiles use the same release name, worker prefix, external
ServiceAccount, PVC and bearer references. Never install them as two production
allocators. The AWS profile can rent one paid GPU indefinitely, with a USD
1.75/hour ceiling plus provider storage/traffic costs.

The current Core provisioner selects one policy provider and one dstack project
per manager. These Helm profiles do **not** implement automatic failover,
simultaneous provider pools or per-family provider routing. Fallback and return
to AWS are explicit operator handoffs with one allocation owner throughout.

The manager and worker image digests and exact worker command are unchanged.
The command SHA256 is
`81b537df1660ac50e4d64142b63f9b99afd537b1a906b7589e00873d4cfbbec0`.
All four proving families, program hashes, architecture check, parallelism and
graceful drain settings are retained. The A10G has nominal 24GB VRAM; the AWS
offer exposes about 22GiB usable, so placement uses a 22GiB minimum. All family
minimums remain 16GiB. The provisional chunk runtime estimate is 360 seconds;
this is not a measured throughput guarantee or a claim of performance parity.

## Prerequisites and bounded placement

The chart does not configure AWS credentials or create provider fleets. Before
starting it, provision and offer-only validate the dedicated dstack fleet
`devnet-provers-aws/devnet-capacity-manager-active-aws-a10g`:

- backend `aws`, region `us-east-1`, instance type `g5.4xlarge`, on-demand;
- nodes 0..1, exactly one A10G with at least 22GiB usable GPU memory;
- minimum 16 CPUs, 64GiB RAM and 200GiB disk;
- hourly instance price ceiling USD 1.75 and an explicit bounded idle policy.

Confirm actual planned resources and price before allocation. Provider offers
and availability can change; a matching instance name alone is insufficient.
A priced offer does not guarantee live EC2 capacity. The isolated lab observed
`InsufficientInstanceCapacity` in two eligible availability zones, followed by
a successful bounded CM retry. If allocation still cannot obtain an instance
within the agreed startup window, treat that as AWS availability exhaustion and
follow the same manual fallback procedure. Stop AWS CM first, then verify
terminal owned tasks and actual provider cleanup; an offer-only result or a
failed task alone cannot establish cleanup. Do not expand price, regions or
instance selectors automatically.

Keep credentials in the existing dstack controller/provider configuration. Do
not add AWS credentials, IRSA annotations or Kubernetes API access to the
manager Pod or ServiceAccount.

The profile requires these external resources in `dstack-system`:

- unannotated ServiceAccount `devnet-capacity-manager-active`, token automount off;
- retained PVC `devnet-capacity-manager-active-state`;
- Secret `devnet-capacity-manager-active-wp-token`, key `proof-work-token`;
- Secret `dstack-controller-auth`, key `admin-token`.

Prepare dstack project Secret `cm_active_worker_token_1013` **inside
`devnet-provers-aws`**, containing the approved worker bearer value. A same-named
Secret in `main` is not available in the AWS project. Check an existing target
Secret for equality before reuse; never overwrite unrelated auth or put a real
token in values. The remote worker token in this profile is only a project
Secret reference. The manager ECR image also requires existing node image-pull
permissions.

## Provider handoff without a second allocator

Save the current applied manifest, policy, actual owned run IDs/provider rental
IDs, PVC identity and state backup. Keep the SDK task retired and its expired
watchdog suspended. Scale the existing manager to zero **with its original
provider configuration** and allow native drain up to the 1800-second grace.
Verify Pods are gone, owned tasks terminal, proof leases zero and actual owned
provider rentals removed before starting AWS. A terminated task or elapsed
deadline alone does not prove provider cleanup. Root/operator owns these live
checks; changing a chart file does not perform this handoff.

Retain the PVC. Reconciliation state is keyed by server URL, project and worker
prefix, so changing `main` to `devnet-provers-aws` selects a different state file
on the same volume. Do not copy or rename the main-project checkpoint into AWS
state, and inspect any retained AWS checkpoint/owned runs before reuse. A new
project configuration cannot inventory or clean up the old project's rentals.
Preserve saved checkpoints and shared auth for diagnosis.

For the raw Deployment to Helm transition, also follow
`capacity-manager-devnet.md`: immutable selectors prevent in-place adoption;
delete only the stopped, backed-up raw Deployment and assign its policy
ConfigMap to the intended release after ownership checks. External SA/PVC and
Secrets remain externally managed. If WP NetworkPolicy is enforced, preserve
its other values and apply the existing
`values/capacity-manager-devnet-wp-peer.yaml` overlay to its release in `default`.

Only after cleanup and preflight, install/update the **same** release:

```bash
helm upgrade --install devnet-capacity-manager-active ../charts/capacity-manager \
  --kube-context "$KUBE_CONTEXT" --namespace dstack-system \
  -f values/capacity-manager-devnet-aws-a10g.yaml
```

Update monitoring's project, fleet, provider inventory, price and metrics epoch
before startup. Verify one exact current ready provider RunID, one actual GPU,
admitted Pod security/image/args, provider resources and price, fresh decisions,
accepted proof results and queue ages. Do not count retained readiness from a
previous RunID. With native shutdown enabled, upgrades/restarts can drain and
replace workers; check cleanup and cold-start readiness each time. Stop and
repair CM on failure; do not silently restore SDK ownership.

## Price/availability preflight and manual fallback

1. Before the first AWS allocation or a provider switch, request an offer-only
   dstack plan for the intended AWS FleetSpec and worker RunSpec. For the run,
   use `get_plan(..., unallocated_resources=True, for_offers_only=True)` and
   inspect `job_plans[].offers`; do not call apply or create as a preflight.
   Keep the existing fleet and instance selectors, then confirm availability,
   exactly one A10G, usable VRAM, CPU/RAM/disk and hourly price at or below USD
   1.75. Check actual ownership/inventory separately: an offer-only plan does
   not prove there are no paid workers. Record a bounded, credential-free result.
2. If no matching available AWS offer meets the price ceiling, leave the
   ceiling unchanged and prepare the qualified RTX3090 fallback described in
   `capacity-manager-devnet.md`. Preflight its current pinned offer, effective
   resources and USD 0.80/hour ceiling; Vast offer IDs are ephemeral. If the
   qualified offer disappeared, qualify a replacement before changing selectors.
   If neither provider has acceptable capacity, leave the manager stopped and
   report the blocker rather than bypassing price or hardware limits.
3. If an AWS worker is already running, use the original AWS configuration to
   drain it and stop the manager as above. Wait for zero leases and terminal
   owned tasks, remove only owned AWS resources, and verify actual owned EC2
   instances are gone. Preserve the manager state PVC, auth and unrelated
   controller resources. Do not start a Vast worker while the old AWS rental
   remains runnable. Update monitoring to the intentional handoff phase before
   stopping so stale AWS assumptions cannot submit another allocator.
4. Verify the fallback project's worker Secret, fleet and retained state, then
   update the **same** Helm release using
   `values/capacity-manager-devnet-rtx3090.yaml`. Use its policy, project `main`,
   fleet, region and instance selectors together; do not mix AWS selectors with
   a Vast project. Changing project selects a separate checkpoint on the same
   PVC. Keep the SDK retired and its watchdog suspended. Verify the new RunID's
   real readiness, accepted proofs, actual single rental and price; start a new
   provider metrics epoch rather than mixing AWS and Vast timings.
5. While on fallback, periodically repeat the bounded AWS offer-only check at
   the existing monitoring cadence. Once an acceptable AWS offer returns,
   prepare the reverse handoff: drain/verify cleanup of the Vast worker and
   provider rental, then update the same release to this AWS-primary profile.
   Verify the new exact AWS RunID and resource/price/security checks. Restoring
   AWS preference must not start a second allocator or resume SDK ownership.

This manual procedure is the supported behavior of these profiles. Automatic
price/availability-based fallback needs a separate Core feature and recovery
qualification; this chart update does not claim to provide it.

## Performance qualification status

The current-image A10G exact-input offline replay produced a valid proof in
**341.262 seconds**, against **253.489 seconds** for the historical SDK and
**218.352 seconds** for the qualified CM RTX3090/EPYC placement. The A10G was
34.6% slower than that SDK sample and 56.3% slower than the RTX3090 sample.
This is one identical chunk input per placement, not a throughput measurement
or evidence that the allocator causes the timing difference. Cold preparation
was 137.051 seconds, recorded separately. The worker binary, cycles, program,
public inputs and canonical verification key were checked. Actual CPU and
memory cgroup limits were unrestricted; a container quota did not explain this
sample. The isolated AWS instance and disk were verified removed afterward.

A stronger L40S candidate is described in `capacity-manager-devnet-aws-l40s.md`.
Its isolated exact-input chunk replay passed in 206.947 seconds. It remains
disabled pending current-image all-family acceptance, external prerequisites
and an approved ongoing price ceiling. The A10G profile is a functional AWS option, **not a
qualified replacement for the RTX3090 performance requirement**. The production
RTX3090 manager remains unchanged during qualification. Earlier all-family AWS
qualification used a different worker image and does not qualify this profile's
performance. All-family current-image acceptance, throughput and Private
Mainnet load qualification remain outstanding.
