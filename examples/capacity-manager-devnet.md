# DevNet Capacity Manager: qualified RTX3090 profile

Use `values/capacity-manager-devnet-rtx3090.yaml` with the independent
`capacity-manager` chart in namespace `dstack-system`. This is a snapshot of the
October 13, 2026 full-mode deployment, not a default for other networks. It can
keep one paid worker running indefinitely; `install-all` remains unchanged.

The profile preserves the pinned manager/worker images, exact worker command,
hash-checked chunk/batch/bridge/aggregation programs and shared proof-work bearer
references. It sets one warm worker, a one-worker ceiling, an instance/pool price
ceiling of USD 0.80/hour and native graceful shutdown with 1800 seconds of grace.
The only policy calibration is the chunk runtime estimate: 240 seconds, based on
seven observed parent totals with a 236-second median. Other family estimates
remain provisional. This does not establish launch throughput or all-family
performance.

## Placement and proof evidence

The qualified fleet is `main/devnet-capacity-manager-active-rtx3090` on dstack
`https://dstack.devnet.doge.xyz`. Its nodes range is 0..1, GPU requirement is one
RTX3090 with 24GiB VRAM, minimum CPU/RAM/disk is 16 CPUs/64GiB/200GiB, reliability
floor is 0.95 and price ceiling is USD 0.80/hour. Actual qualified offer
`55816748` in Netherlands provided an EPYC7402P, 48 available CPUs and a measured
46.08-CPU quota, at USD 0.64548/hour including the selected disk.

The manager and fleet both pin this offer ID. **Vast offer IDs are ephemeral.**
Before a future replacement, validate that the offer is still available and
meets effective resource and price requirements; if it has disappeared, qualify
a new offer and update both selectors through a lease-safe change. Do not fall
back silently to the cheapest RTX3090 or assume core count/score establishes
CPU performance. The chart does not create fleets, rent a second GPU or provide
automatic provider failover.

The identical historical chunk witness/program/binary and 109,938,530 cycles
were replayed and cryptographically validated:

| Placement | SDK-compatible proving wall time |
|---|---:|
| Previous SDK RTX3090 |253.489s|
| Initial CM RTX3090 on Xeon |311.579s|
| Qualified CM RTX3090 on EPYC |218.352s|

Cold key preparation was excluded. The offline replay did not submit a
production proof. Seven subsequent live eager chunk proofs were accepted by the
coordinator; their parent total median was 236.04s. Those input mixes differ from
the historical SDK mix, and eager work is separate from leased workflow
throughput. This evidence supports this placement, not universal parity or
exclusive CPU causation.

## Existing credentials and state

The profile reuses these externally managed resources in `dstack-system`:

- unannotated ServiceAccount `devnet-capacity-manager-active`, with token
  automount disabled;
- PVC `devnet-capacity-manager-active-state` (1Gi, gp3), containing the existing
  reconcile checkpoint;
- Secret `devnet-capacity-manager-active-wp-token`, key `proof-work-token`;
- Secret `dstack-controller-auth`, key `admin-token`.

The remote worker token is the dstack **project Secret reference**
`cm_active_worker_token_1013`, not a credential in values. No Secret is created
by this profile. Check the Secret references, account metadata and retained PVC
before installing; never copy real token values into this repository. A fresh
deployment must provision these external resources first or explicitly choose
chart-created account/state with fresh names. Do not replace an existing
checkpoint with an empty claim to bypass ownership conflicts.

The pinned manager digest currently lives in the DevNet ECR registry. EKS node
image-pull permissions are required; the manager account receives no IRSA role.
This is independent of the generic chart's GHCR image workflow/release.

## Raw Deployment to Helm handoff

This PR does not perform the handoff or change live services. The raw Deployment
and chart have different immutable Pod selectors, so do not try to adopt the raw
Deployment in place, run a second manager, or use a new worker prefix/PVC.

1. Save the exact current Deployment, policy, ServiceAccount references, PVC
   identity, manager image, worker command and provider inventory privately.
   Confirm the SDK task/fleet are retired and its old watchdog remains suspended.
2. Check the currently running GPU's real-mode readiness, image/program pins,
   fleet/offer, price and state. Dry-run the chart with a separate review name;
   do not start an allocator as a rendering test.
   Set existing monitoring to an explicit operator-owned handoff phase before
   changing resources. Update its expected admitted manifest, Pod selector and
   mount-path checks from the reviewed Helm render: this chart labels Pods with
   `app.kubernetes.io/name=capacity-manager` and
   `app.kubernetes.io/instance=devnet-capacity-manager-active`, rather than the
   raw Deployment's name label. Otherwise the old raw-manifest monitor could
   mistake an approved change for missing Pods or security drift. Continue
   watching drain/provider inventory; do not let monitoring restore SDK or the
   old raw Deployment independently.
3. Scale the **existing raw manager** to zero with its original configuration.
   Its native shutdown drains owned workers. Allow up to 30 minutes; verify
   manager Pods are gone, owned tasks terminal, proof leases zero and provider
   inventory reconciled. A termination deadline alone does not prove cleanup.
   Preserve the existing PVC, Secrets, ServiceAccount and dedicated fleet.
4. Revalidate the pinned fleet offer after drain, since replacement will need a
   fresh rental. If it is unavailable, leave the manager stopped and qualify a
   replacement; do not enable SDK or relax spend/hardware constraints.
5. Delete only the stopped raw Deployment after saving it. Its old immutable
   selector cannot be patched to the chart selector. Assign the existing policy
   ConfigMap to the intended Helm release only after checking no other release
   owns it. Keep account/state externally managed as the profile specifies:

   ```bash
   kubectl --context "$KUBE_CONTEXT" -n dstack-system annotate configmap \
     devnet-capacity-manager-active-policy \
     meta.helm.sh/release-name=devnet-capacity-manager-active \
     meta.helm.sh/release-namespace=dstack-system
   kubectl --context "$KUBE_CONTEXT" -n dstack-system label configmap \
     devnet-capacity-manager-active-policy app.kubernetes.io/managed-by=Helm --overwrite
   ```

6. If WP's NetworkPolicy is enforced, overlay
   `values/capacity-manager-devnet-wp-peer.yaml` on its **existing** release in
   `default`. It admits only this Helm release in `dstack-system` to the
   proof-work port (9300), not the public API. Preserve WP's other values; render
   the policy before applying. The raw manager's old Pod label is different.
7. Explicitly install the independent release, using the reviewed chart/profile:

   ```bash
   helm upgrade --install devnet-capacity-manager-active ../charts/capacity-manager \
     --kube-context "$KUBE_CONTEXT" --namespace dstack-system \
     -f values/capacity-manager-devnet-rtx3090.yaml
   ```

8. Verify exactly one current provider run and GPU, binding worker readiness to
   its new run ID. Check current CPU/GPU limits, accepted proof results, queue
   ages, fresh decisions, errors and spend. Compare identical inputs or report
   workload differences. Verify monitoring now checks the Helm admission
   contract and current run ID, then leave the handoff phase. Keep the SDK
   watchdog suspended.

Because this profile sets `scaleDownOnShutdown: true`, manager upgrades/restarts
may drain and replace workers. Preserve enough grace, expect cold-start time,
and verify rental cleanup. Uninstall does not delete the external PVC/Secrets/SA;
it also does not prove remote instances have disappeared. On failure, stop CM,
inspect native drain/provider cleanup and repair the CM configuration. Do not
silently restore SDK allocation ownership.
