# Alert ownership and duplicate removal

Service diagnostics are enabled by default. The catalog contains 91 service-specific
rules after removing repeated scrape and Pod checks. Common infrastructure rules
remain active independently of the service catalog.

The tables below identify the retained owner for each removed rule. Removed custom
rules are deleted from the source catalog. Duplicate kube-prometheus-stack rules
are disabled through `defaultRules.disabled`, so they are absent from the rendered
PrometheusRule resources rather than merely silenced in Alertmanager.

## Removed custom definitions

| Removed rule | Retained owner |
| --- | --- |
| `L2RethMetricsTargetDown` | MetricsTargetDown |
| `L2RethPodNotReady` | BusinessPodNotReady / KubePodNotReady |
| `WithdrawalProcessorMetricsTargetDown` | MetricsTargetDown |
| `WithdrawalProcessorPodNotReady` | BusinessPodNotReady / KubePodNotReady |
| `CubesignerSignerMetricsTargetDown` | MetricsTargetDown |
| `CubesignerSignerPodNotReady` | BusinessPodNotReady / KubePodNotReady |
| `EthDaSubmitterMetricsTargetDown` | MetricsTargetDown |
| `EthDaSubmitterPodNotReady` | BusinessPodNotReady / KubePodNotReady |
| `L1InterfaceMetricsTargetDown` | MetricsTargetDown |
| `L1InterfacePodNotReady` | BusinessPodNotReady / KubePodNotReady |
| `TsoServiceMetricsTargetDown` | MetricsTargetDown |
| `TsoServicePodNotReady` | BusinessPodNotReady / KubePodNotReady |
| `ProofCoordinatorMetricsTargetDown` | MetricsTargetDown |
| `ProofCoordinatorPodNotReady` | BusinessPodNotReady / KubePodNotReady |
| `FeeOracleMetricsTargetDown` | MetricsTargetDown |
| `FeeOraclePodNotReady` | BusinessPodNotReady / KubePodNotReady |
| `BusinessPodRepeatedRestarts` | BusinessPodContainerRestarted |
| `DstackControllerUnavailable` | BusinessDeploymentReplicasDegraded / BusinessDeploymentUnavailable |

## Replaced upstream definitions

| Removed upstream rule | Retained owner |
| --- | --- |
| `TargetDown` | MetricsTargetDown |
| `CPUThrottlingHigh` | ContainerCPUThrottlingHigh |
| `NodeCPUHighUsage` | NodeCPUUsageHigh |
| `NodeMemoryHighUtilization` | NodeMemoryUsageHigh / NodeMemoryUsageHighCritical |
| `NodeFilesystemSpaceFillingUp` | NodeDiskFillingUp / NodeDiskFillingUpCritical |
| `NodeFilesystemAlmostOutOfSpace` | NodeDiskUsageHigh / NodeDiskUsageHighCritical |
| `NodeFilesystemAlmostOutOfFiles` | NodeDiskInodesHigh / NodeDiskInodesHighCritical |
| `KubePersistentVolumeFillingUp` | PVCUsageHigh / PVCFillingUp (warning and critical) |
| `KubePersistentVolumeInodesFillingUp` | PVCInodesHigh / PVCInodesHighCritical / PVCInodesFillingUp |
| `KubePodCrashLooping` | BusinessPodCrashLooping |
| `KubeDeploymentReplicasMismatch` | BusinessDeploymentReplicasDegraded / BusinessDeploymentUnavailable |
| `KubeStatefulSetReplicasMismatch` | BusinessStatefulSetReplicasDegraded / BusinessStatefulSetUnavailable |
| `KubeJobFailed` | BusinessJobFailed |

## Coverage and semantics

- `MetricsTargetDown` checks every discovered target independently for five
  minutes. A healthy replica cannot mask a failed target; the former upstream
  rule aggregated failed targets into a percentage.
- `BusinessPodNotReady` covers running, unready Pods cluster-wide. The retained
  upstream `KubePodNotReady` covers Pending, Unknown and Failed phases. Their
  current phase selectors do not overlap. Job and terminating-Pod exclusions
  remain in the running-Pod check.
- Crash loops, Deployment/StatefulSet availability, terminal Job failures and CPU
  throttling use cluster-wide replacement rules. Historical `Business*` names
  remain for compatibility. Other container resource and restart-event rules
  retain their configured business selectors.
- All PVC rules now cover every namespace. Node filesystem rules retain their
  real-filesystem and mountpoint filters. Static capacity/inode thresholds and
  predicted exhaustion are different signals. PVC inode forecasting remains
  covered by `PVCInodesFillingUp`, including the upstream read-only and explicit
  exclusion safeguards; deleting the upstream family does not remove forecasting.
- Node CPU and memory retain scroll-monitor's configurable thresholds. Memory
  warning/critical bands are mutually exclusive. CPU throttling retains the
  25-percent, 15-minute defaults.
- Replica unavailability and degraded replicas retain their separate critical and
  warning conditions. Upstream rollout/generation, DaemonSet scheduling and node
  health checks with distinct semantics remain available.
- WF protocol progress, replay progress, L2 batch progress, application readiness,
  Kubernetes readiness and internal error counters observe different conditions.
  They can correlate during an incident without being interchangeable rules.

Disabling a retained owner via `diskAlerts`, `resourceAlerts` or
`businessPodAlerts` also disables its coverage. Re-enable the corresponding
upstream rule explicitly if using that upstream implementation instead.
Existing Grafana installations need explicit removal of retired rules; seeding
preserves operator-owned resources. The devnet Prometheus migration has no stored
Grafana metric rules to retire.
