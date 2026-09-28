# Official Node Sync

Node Sync can observe the already deployed bootnodes, internal RPC nodes and
public RPC nodes. The sequencer supplies the reference chain; it is not evidence
that a follower can synchronize. This mode does not require a separately operated
canary. It measures the selected official fleet, not permissionless bootstrap,
third-party connectivity or a fresh synchronization from genesis.

Select `statusPage.publication.nodeSync.mode: official` in the monitoring values:

```yaml
statusPage:
  publication:
    nodeSync:
      mode: official
      namespace: "" # Node namespace; empty uses the monitoring Helm namespace.
      image: python:3.12.11-alpine3.22
      reference:
        values: l2-reth-sequencer-production.yaml
        release: l2-reth-sequencer
        role: sequencer
      followers:
        - values: l2-reth-bootnode-production.yaml
          release: l2-reth-bootnode
          role: bootnode
        - values: l2-reth-rpc-production.yaml
          release: l2-reth-rpc
          role: internal-rpc
        - values: l2-reth-rpc-public-production.yaml
          release: l2-reth-rpc-public
          role: public-rpc
    components:
      node-sync: {mode: observe, rule: {builtin: true}}
```

These are source-selection examples, not a claim that these releases are installed.
Use the effective values filename and actual Helm release for each deployed node.
For numbered bootnode releases, add one entry per release (for example `...-0.yaml`
and `...-1.yaml` with their corresponding releases). Do not add inactive base
files. Choose exactly one active sequencer with one replica and
`reth.sequencer.allowEmptyBlocks: true`. Standby sequencers are not automatic
fallback references. An on-demand chain needs a reviewed custom rule.

Run the existing offline `scrollsdk setup status-page` or `setup prep-charts`
generator. The CLI validates source roles and chain IDs and derives each Service
name, HTTP RPC port and expected replica count. It honors `service.main.fullname`,
chart/global name overrides and the common chart's release naming. If a Service
name contains Helm template expressions, supply its reviewed rendered name as
`service` on that source entry. A selected follower with `controller.replicas: 0`
is excluded; at least one follower must remain. Regenerate after source files,
release naming or replica counts change. HPA/dynamic fleet changes require a
matching updated generation; they are not silently treated as complete evidence.

The chart installs a single small Python collector, a private metrics Service and
a ServiceMonitor. It lists EndpointSlices in the selected namespace, selects the
configured Services, deduplicates by Pod UID and contacts Pod IPs directly. This
avoids a load balancer repeatedly sending every probe to the same healthy replica.
Kubernetes recommends EndpointSlice for Service endpoint discovery; the legacy
Endpoints API is deprecated. See the [Kubernetes Service documentation](https://kubernetes.io/docs/concepts/services-networking/service/#endpoints-deprecated).

The collector has a dedicated ServiceAccount with namespace-scoped `list` on
`discovery.k8s.io/endpointslices`. RBAC cannot constrain list access by Service
label; the client applies that selector. It has no Secret access, writes, exec or
cluster-wide role. Monitoring and nodes may use different namespaces; configure
`namespace` and allow collector egress to the Kubernetes API and node HTTP ports,
and Prometheus access to the collector on 9112 where NetworkPolicies restrict it.
There is no public ingress and no Instatus credential in this workload. The
existing Grafana/delivery flow remains responsible for public updates.

Each approximately 30-second round checks:

1. Exact expected Pod population for every selected Service; no overlapping Pod
   identities across Services. Endpoint membership must stay stable for the round.
2. A ready sequencer with the expected chain ID and recent latest block (default
   `health.maxBlockAgeSeconds: 120`). A stopped or inaccessible reference means
   unknown, even if every follower has the same stopped head.
3. Each follower's chain ID, latest head, and block hash at the lower of its height
   and the sampled reference height. Lag uses the reference chain's block timestamps,
   not a guessed block rate (default `health.maxNodeLagSeconds: 120`).
4. Stable comparison blocks and reference anchor across the round. A detected
   reorg invalidates the sample rather than publishing a transient fork or recovery.

A not-ready follower, wrong chain, persistent same-height hash mismatch or excessive
lag produces affected evidence. Missing/extra Pods, incomplete discovery, RPC errors,
an invalid reference or a changing sample produce unknown. Healthy requires all
selected follower Pods to pass. An affected replica cannot be averaged away by
healthy siblings. Defaults retain 5 minutes of failure confirmation and 10 minutes
of verified recovery through the existing delivery verifier.

Metrics are `scroll_status_node_sync_affected` and
`scroll_status_node_sync_timestamp_seconds`, plus per-Pod diagnostic
`scroll_status_node_sync_member_affected`. The observation-valid metric includes
a bounded failure reason for internal diagnosis. Unknown rounds omit affected evidence.
PromQL requires one fresh, binary aggregate from the collector. This internal
observation is separate from `minimumProbeLocations`; independent public probes
are still required for public RPC and web components. The collector reads only
`eth_chainId` and `eth_getBlockByNumber` without full transaction objects, caps
responses at 2 MiB and bounds a round to 60 seconds. At most 32 follower Pods are
supported; slow/oversized rounds cannot manufacture healthy evidence.

Existing configurations retain `mode: external` for compatibility. To select an
external canary instead, set `reference: {}`, `followers: []` and configure
`probes.nodeRpcUrl` plus `probes.nodeDependencyChecks` at each independent probe
site. Official mode excludes these canary fields from exported probe configuration;
private Service/Pod details never enter the Instatus component catalog. This is a
choice of built-in health source; combining both sources requires a custom rule.
