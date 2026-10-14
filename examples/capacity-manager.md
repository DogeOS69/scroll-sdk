# Core capacity-manager deployment

This is an optional alternative to SDK `setup proof-workers`, not another
controller for the same worker session. Core computes capacity from WP prove
backlog and owns worker lifecycle; dstack still provisions the cloud instances.
`install-all` never installs it. Installing the independent release is the
explicit paid-resource action; with the example policy it keeps one worker warm.

## Release and infrastructure prerequisites

The integration targets Core commit
`350508c1cd068230fc731747a3b5bbfbb44b81cf` (native dstack price ceiling, manual
provider switching). The normal proof-coordinator image does not contain this
binary. Obtain a compatible, published Capacity Manager image and its immutable
digest from the Core release owner, then set `image.repository` and
`image.digest` in the spec. Verify that the selected image provides
`/usr/local/bin/capacity-manager` with `--dstack-max-price-usd` and
`--provisioner-state-dir`. The SDK chart consumes that image directly; image
building and publication are managed outside this repository. Generic and DevNet
examples pin `dogeos69/capacity-manager:develop-50653e7b` by its immutable digest.
The manager image is independent of the existing proof worker/circuit release:
keep the compiler-checked worker image and published program bundle unchanged.
Selecting L4 requires the worker image check to report CUDA architecture 89.
WP must expose `GET /v1/proof-work/capacity/summary` on its proof-work listener
and accept the deployment's proof-work bearer token. Qualify this API against the
selected WP image; the manager image alone does not add the endpoint to WP.

Configure stock dstack 0.21.5 with a **dedicated project and existing fleet** for
this deployment. Core's `docs/engineering/aws-gpu-dstack.md` and
`tools/real-proving/dstack/server-aws.yml.example` describe AWS credentials, role,
VPC, quota and fleet setup. The SDK does not invent these infrastructure values
or provision an AWS fleet in this step. The declared fleets/regions/instance
types must exist in that project. Provider selection is explicit; there is no
automatic AWS-to-Vast failover. AWS provisioning IAM belongs to dstack; the
manager Pod receives no AWS credentials or Kubernetes API token.

## Prepare and start

1. Retire any existing SDK worker session using `setup proof-workers status` and
   `destroy`; confirm provider instances/fleets are gone. Remove `proofWorkers`
   from spec and add `capacityManager` from `capacity-manager-spec.example.yaml`.
2. Run the normal staged setup through `setup render` and `setup upload-secrets`.
   The `prep-charts` integration consumes the compiler worker contract, image check and
   verified publication receipt. It generates the policy and command in
   `values/capacity-manager-production.yaml` and adds only the manager peer to
   WP's proof-work NetworkPolicy. It never allocates GPUs.
3. Install/upgrade WP and Proof Coordinator, and install dstack using the normal
   deployment targets. They provide the existing proof token Secret and dstack
   credentials. Use the deployment namespace and Kubernetes context consistently.
4. Explicitly install the manager. Make synchronizes credentials first:

```bash
# From the spec directory, enter setup plan's conventional output directory.
cd deployment
make install-withdrawal-processor KUBE_CONTEXT="$KUBE_CONTEXT" NAMESPACE="$NAMESPACE"
make install-capacity-manager KUBE_CONTEXT="$KUBE_CONTEXT" NAMESPACE="$NAMESPACE"
scrollsdk setup capacity-manager status --dir . --kube-context "$KUBE_CONTEXT"
```

`make install-capacity-manager` waits for dstack's rollout, checks the named fleets,
and synchronizes the existing worker token into the dstack project's Secret store.
The proof chart's ExternalSecret must have synchronized the token first. A failed
preflight stops before Helm; fix the cause and retry the same Make target.
The controller must be running because dstack 0.21.5 registers project Secrets
through its API, not its startup YAML. This idempotent preflight creates no fleets
or runs. Only the subsequent Helm installation can start GPU allocation.

The manager references the existing controller auth Secret in the same namespace;
it does not create another copy of the admin token. WP's existing `proof-work-token`
is also mounted by reference. `gen-secrets` and `push-secrets` retain their existing
credential generation/publication responsibilities; neither requires a running
dstack server. No token is written to values, stdout, or a ConfigMap.

Before chart publication, use the local chart explicitly:
`make install-capacity-manager CAPACITY_MANAGER_CHART=../scroll-sdk/charts/capacity-manager`.
Deploy WP chart 0.1.26 or newer so the generated manager peer is rendered.
All spec-managed releases use `infrastructure.namespace` (default `default`).
The manager, dstack, proof services and generated WP peer share this namespace.
The [DevNet profile](capacity-manager-devnet.md) describes a historical manual
installation; its cross-namespace layout is not the normal spec deployment path.
There is no public ingress or inbound service for the manager.

Preparation creates `.scrollsdk/capacity-manager/plan.json`. A conflicting SDK
worker session stops preparation. SDK `proof-workers apply` refuses this marker
or capacityManager intent, while `status` and `destroy` remain available for
cleanup. This prevents simultaneous use through these CLI entry points; direct
Helm/dstack actions and other deployment directories remain operator-controlled.

## Operate, restart and retire

The Deployment uses one replica, Recreate updates and a retained state PVC.
The state is required for adoption, failure cooldowns and cleanup after restart;
never delete it to bypass an ownership/fingerprint conflict. A Pod becoming Ready
only indicates its process started, not that GPU workers are healthy: inspect
manager logs, dstack inventory and Coordinator proof progress.

By default `scaleDownOnShutdown` is false: upgrades and process restarts leave
remote workers running for the next instance to adopt. **Pausing/scaling to zero,
uninstalling Helm, or losing the manager does not stop GPU billing.**

For intentional retirement, retain the old image, command, project, prefix and
state, set `manager.scaleDownOnShutdown: true` in its existing values, upgrade
that same release, wait for the new manager to start, then scale its Deployment
to zero. Core drains according to active proof leases and reconciles its owned
runs. Set termination grace long enough for the workload/provider; a Kubernetes
kill at the deadline does not prove cleanup completed. Verify dstack and provider
inventory, and retry cleanup with the old configuration if any rentals survive.
Core stops its runs; dstack fleet idle behavior controls instance release. Remove
an unused fleet through dstack only after confirming it contains no other work.

Only after confirmed retirement may an operator archive the local plan and old
state and choose a new worker prefix/state PVC for a new provider or worker
fingerprint. New configuration generation deliberately refuses to silently change
an existing plan's identity. Never run two manager instances against the same
state/prefix, or the SDK launcher against the same deployment's capacity.

The examples cap instance offers at USD 1.50/hour (AWS L4) or USD 0.80/hour (Vast
RTX4090), with one warm worker and at most two. These are configuration limits,
not live prices; storage, transfer and taxes are outside them. Runtime estimates
are initial Core example values and should be calibrated using real proofs.
Set `minWorkers: 0` for scale-to-zero when there is no prove backlog. Core submits
long-running dstack tasks (`max_duration: off`); no 48-hour rental limit is added.
The fleet must provide enough CPU, RAM and disk for the selected worker image.

## Validation boundary

Chart rendering, CLI generation/credential tests and Core argument contract
checks run without allocating GPUs. A live rollout must still qualify the
published manager executable, WP API compatibility, dstack fleet placement,
provider startup, real proof completion, restart adoption and confirmed cleanup.
