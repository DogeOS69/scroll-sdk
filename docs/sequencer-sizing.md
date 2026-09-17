# Sequencer configuration and sizing recommendations

## Recommended starting point

For a DogeOS reth sequencer targeting **10 million gas per block and a 3-second
block interval**, start with an **8-vCPU / 32-GiB resource envelope per sequencer**,
SSD-backed persistent storage, and separate nodes for public RPC traffic.
Keep this envelope until a longer workload test justifies changing it.

This is a conservative deployment recommendation based on the September 16,
2026 devnet test and the existing SDK example. It is **not a measured minimum
hardware requirement or a production throughput guarantee**. The test measured
container usage on existing Kubernetes nodes; it did not benchmark a dedicated
8-vCPU machine, compare CPU models, or test smaller resource limits.

| Setting | Recommended starting value | Basis and qualification |
|---|---|---|
| CPU limit | 8 cores per sequencer | Retains the tested limit and the SDK example's headroom. |
| Memory limit | 32 GiB per sequencer | Retains the tested limit; measured working set peaked at about 3.2 GiB. |
| CPU request | 2 cores per sequencer | Proposed scheduling allowance, not a tested minimum; the test used 1 core. |
| Memory request | 4 GiB per sequencer | Above the observed 2.8–3.2 GiB working set; the tested 2-GiB request was below actual usage. Increase it if sustained usage grows. |
| Persistent storage | SSD-backed, expandable PVC; initially 1000 GiB for a long-lived deployment | Matches the sequencer production example. The devnet used a 100-GiB PVC; neither size establishes a retention or IOPS guarantee. |
| Builder gas limit | `10000000` | The limit exercised by the test. |
| Block interval | `3000` ms | All measured block intervals were 3 seconds. |
| Payload building duration | `800` ms | Existing sequencer example setting; not independently tuned by this test. |
| Placement | Separate failure domains for separately configured sequencers; public RPC on dedicated RPC nodes | Operational recommendation to reduce resource contention and correlated failures. |

CPU and memory limits are container ceilings, not dedicated host allocations.
Budget node allocatable capacity for the sequencer, system components, and other
workloads. Requests guide Kubernetes scheduling; CPU limits can cause throttling,
and memory limits can lead to OOM termination. See the official
[Kubernetes resource management documentation](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/).

Do not size storage from this short run alone. Measure database growth, free
space, write latency, and catch-up behavior on the intended storage class before
setting a retention target. A larger PVC does not by itself prove sufficient
I/O performance.

## Suggested values overlay

Apply this **partial overlay** to an otherwise complete, deployment-specific
[sequencer production values file](../examples/values/l2-reth-sequencer-production.yaml).
It does not supply the image pin, chain identity, genesis, signer, peers, or
service account. The higher requests below are recommendations; they have not
been applied to the SDK defaults or the devnet by this document.

```yaml
resources:
  requests:
    cpu: "2"
    memory: 4Gi
  limits:
    cpu: "8"
    memory: 32Gi

reth:
  builderGasLimit: "10000000"
  data:
    size: 1000Gi
    accessMode: ReadWriteOnce
    retain: true
  sequencer:
    blockTimeMs: "3000"
    payloadBuildingDurationMs: "800"
```

The [l2-reth chart](../charts/l2-reth/README.md) permits only zero or one replica
for a sequencer release. Deploy additional sequencers as separate configured
releases with their own identity and storage. Follow the deployment's sequencing
and failover procedure; replica count alone does not provide coordinated
failover or authorize multiple producers.

## Reference test: September 16, 2026

### Scope and execution

- Run ID: `k8s-stress-20260916T041939Z`.
- Window: **04:19:39–04:40:04 UTC**, approximately 20 minutes including setup,
  calibration, funding, load, drain, and recovery.
- Rollup image: `dogeos69/rollup-node:v0.3.0-beta.1c`.
- Observed sequencer pods: `l2-reth-sequencer-0-0` and
  `l2-reth-sequencer-1-0`; their measurements are reported separately, not as
  evidence of two independent concurrent block producers.
- Each pod had CPU request/limit **1/8 cores** and memory request/limit
  **2/32 GiB**. Cluster resources and block parameters were not changed for the run.
- Nine load stages, each approximately **60 seconds**: native transfers at
  10, 100, and 200 TPS; Keccak computation and cold storage writes at 50%, 100%,
  and 150% of the configured gas capacity.
- Gas was measured from successful receipts, not inferred from `gasLimit`.
  Computation used **997,088 gas/transaction** and storage writes used
  **979,150 gas/transaction**, with a 1,000,000 gas transaction limit.

All **19,818 transactions** eventually succeeded, with no reverts or unresolved
transactions. The computation and storage workloads both met the test's
sustained-full-block criterion: actual block gas utilization of at least 95%,
at least 10 full blocks, and at least 80% full blocks in the measurement window.
These are test acceptance thresholds, not an industry-wide capacity standard.

### Throughput and block production

| Workload | Submitted transactions | Full blocks / measured blocks | Observed block interval | Additional drain and observation time |
|---|---:|---:|---|---:|
| Transfers, 10 TPS | 600 | 0 / 19 | 3 s | 2.33 s |
| Transfers, 100 TPS | 6,000 | 0 / 20 | 3 s | 2.93 s |
| Transfers, 200 TPS | 12,000 | 19 / 20 | 3 s | 22.56 s |
| Computation, 100% gas load | 201 | 18 / 20 | 3 s | 6.16 s |
| Computation, 150% gas load | 301 | 18 / 19 | 3 s | 36.12 s |
| Storage writes, 100% gas load | 205 | 18 / 20 | 3 s | 5.78 s |
| Storage writes, 150% gas load | 307 | 19 / 20 | 3 s | 36.64 s |

The 200-TPS input rate created a queue. Throughput including drain was about
**145.34 TPS**, so this run does not demonstrate sustainable 200 TPS. At 150%
computation load, measured gas throughput was about **3.31 Mgas/s**, close to
the configured budget of 10 Mgas / 3 s = **3.33 Mgas/s**. Offering 150% load
increased queueing; it did not increase the block gas limit.

### CPU measurements

Values below are cores used, taking the maximum sample across each load stage
and its drain phase. They are **peaks of a one-minute CPU rate**, not instantaneous
execution peaks.

| Workload | Sequencer-0 CPU peak | Sequencer-1 CPU peak |
|---|---:|---:|
| Transfers, 10 TPS | 0.013 | 0.023 |
| Transfers, 100 TPS | 0.066 | 0.141 |
| Transfers, 200 TPS | 0.135 | 0.238 |
| Computation, 100% gas load | 0.055 | 0.092 |
| Computation, 150% gas load | 0.057 | 0.086 |
| Storage writes, 100% gas load | 0.015 | 0.018 |
| Storage writes, 150% gas load | 0.015 | 0.021 |

Both sequencers had zero observed CPU throttling in the saved samples. Their
whole-run CPU peaks were approximately **1.7% and 3.0% of the 8-core limits**.
Full gas utilization did not imply full CPU utilization for these workloads.
The evidence is consistent with queueing at the configured gas budget rather
than sustained CPU saturation; it does not rule out short execution spikes.

### Memory measurements

Memory is the container **working set**, in MiB, rather than a process-heap-only
measurement. One GiB is 1024 MiB.

| Metric | Sequencer-0 | Sequencer-1 |
|---|---:|---:|
| Baseline mean | 2,887.9 MiB | 3,252.9 MiB |
| Whole-run peak | 2,905.1 MiB (2.84 GiB) | 3,267.4 MiB (3.19 GiB) |
| Peak increase above baseline | 17.2 MiB | 14.5 MiB |
| Recovery mean | 2,897.4 MiB | 3,267.1 MiB |
| Peak / 32-GiB limit | 8.9% | 10.0% |
| Container restarts, before → after | 0 → 0 | 0 → 0 |

No OOM kill was observed. Memory stayed close to baseline, but the short run
cannot establish long-term cache growth, absence of leaks, or memory needed
during restart and state catch-up. In particular, a 3.2-GiB observed peak does
not establish a safe 4-GiB **limit**; the suggested 4 GiB above is a **request**.

## Validation before reducing resources or increasing capacity

The recommended envelope leaves room for conditions absent from this test.
Before reducing limits, increasing block gas, or shortening the block interval:

1. Repeat transfer, computation, and storage workloads at the proposed settings,
   including overload followed by drain. Record offered and completed rates
   separately and use actual successful gas consumption.
2. Run a sustained soak, initially at least 24 hours as an operational target,
   and exercise restart/catch-up against a representative chain state. This
   duration is a recommendation, not a completed test or proof of safety.
3. Measure block-building latency, inclusion latency, CPU throttling, memory,
   disk latency/free space, and txpool growth. Record host contention as well as
   container usage, especially if public RPC or tracing is colocated.
4. Use CPU samples with enough resolution to see execution bursts. The saved
   report used a one-minute rate evaluated every 15 seconds; each 60-second
   stage contains only a few samples and mixes neighboring work. Memory is a
   sampled gauge and can also miss brief peaks.
5. Verify that DA and proof backlogs recover independently of sequencer health.
   This run ended with L2 txpools empty and DA pending transactions at zero,
   but still had proof backlog. It did not establish end-to-end withdrawal
   capacity or full-pipeline recovery.

There is no measured safe smaller-node profile, sustained TPS maximum, minimum
IOPS requirement, or long-term storage-growth estimate in this test. Do not
extrapolate a linear CPU-to-TPS scaling factor from these samples.

## Evidence and reproduction

The operator's sibling deployment checkout contains the
[sequencer acceptance summary](../../dogeos-aws-devnet/artifacts/acceptance/gas-capacity-20260916/README.md).
That link requires the `dogeos-aws-devnet` checkout alongside `scroll-sdk`.
The tables above make the measured results available within this repository.

The original core run directory is
`e2e/performance-results/k8s-stress-20260916T041939Z/` in the `dogeos-core`
checkout. Relevant artifacts are `report.md`, `impact.json`, `prometheus.json`,
`phases.json`, `pods-before.json`, `pods-after.json`, the sequencer result JSON,
and `gas-calibration.json`. Tool fingerprints are in `tool-source-sha256.json`.
Do not copy the entire run directory into documentation: it also contains
private test-wallet material.

Execution caveat: the measurement and report generation completed, and Vitest
exited successfully. The outer Bash wrapper exited with code 2 after a script
edit during execution caused an EOF parsing error. This is recorded in the
original manifest; the wrapper exit must not be reported as a clean success.

To reproduce the workload on an explicitly selected test deployment, use the
stress runner documented in `dogeos-core/e2e/scripts/README-stress.md`:

```bash
KUBE_CONTEXT='<explicit-test-cluster-context>' \
DOGEOS_PERF_DEPLOYMENT_DIR='<deployment-checkout>' \
npm --prefix e2e run stress -- --suite sequencer \
  --rates 10,100,200 --stage-seconds 60 --gas-ratios 0.5,1,1.5 \
  --baseline-seconds 60 --recovery-seconds 60 --flow-timeout 1800
```

Run this from the compatible core checkout, with its documented test funding
and configuration prepared. Record the exact image and hardware for each new
run; the old measurements are not a substitute for validating a new release.
