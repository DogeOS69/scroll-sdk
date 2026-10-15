# dstack controller

An independent Helm release for the dstack server, maintained by DogeOS. Runs
on CPU nodes in the existing Kubernetes cluster and can manage multiple GPU
providers through native dstack project/backend configuration. No GPU nodes are
required in the controller's cluster.

Reference: [Nebius dstack chart](https://github.com/nebius/nebius-k8s-applications/tree/33d14191284544d986a60e2ff56f0de690d597d6/dstack/chart).
See `NOTICE` and `LICENSE` for attribution. This chart removes Nebius-specific
configuration and does not depend on the Nebius chart or its marketplace.

## Scope and defaults

- Official dstack **0.21.5** image pinned by multi-platform digest.
- One controller with a `Recreate` upgrade strategy; no HPA. `replicaCount: 0`
  pauses management. PostgreSQL mode also remains single replica in this release.
- ClusterIP service; optional Ingress/TLS; no Kubernetes RBAC grants and no
  service-account token automount by default.
- SQLite on a retained 10Gi PVC by default; external PostgreSQL supported.
  The entire `/root/.dstack/server` directory is persisted, including local logs.
- Configuration, admin token, database URL and cloud credentials reference
  **existing Kubernetes Secrets**, which may be populated by External Secrets.
  The chart generates no credentials. Use Secret references rather than
  plaintext credential values in `extraEnv` to keep secrets out of Helm release data.
- No provider-specific backend defaults, fleet/task manifests, install hooks,
  worker deployment, GPU rental or resource cleanup jobs.

Installing a fresh controller does not submit work. Restoring an existing
database can resume previously submitted work. Stopping/uninstalling the
controller does **not** release remote GPU instances or stop their billing.
Worker pool/fleet/task configuration and Proof Coordinator integration belong
to the deployment tooling, separately from this chart. `scroll-sdk-cli` supports
an optional `dstackController` configuration block in DeploymentSpec and
doge-config, generating `values/dstack-controller-production.yaml` through
`setup generate-from-spec --with-values` or `setup prep-charts`. Generated values
already include the production overrides. This remains an independent release,
outside the umbrella chart; see the CLI's `docs/dstack-controller.md`.

## Prerequisites and configuration

Provide these Secrets in the release namespace before installation:

| Default Secret | Key | Contents |
| --- | --- | --- |
| `dstack-controller-config` | `config.yml` | Native dstack server configuration, including project backends and AES encryption keys |
| `dstack-controller-auth` | `admin-token` | Random admin token used when initializing a new database |
| `dstack-controller-database` (PostgreSQL profile) | `database-url` | `postgresql+asyncpg://user:password@host:5432/dstack` |

Secret names/keys are configurable through `serverConfig`, `auth` and `database`.
Use your existing External Secrets installation or provision the Secrets
separately. There is no External Secrets operator dependency in this chart.

For a new controller without any compute backends, the **Secret's config.yml**
has this structure (replace the placeholder securely; do not commit the key):

```yaml
projects:
  - name: main
    backends: []
encryption:
  keys:
    - type: aes
      name: primary
      secret: <base64-encoded random 32-byte AES key>
```

dstack does not substitute shell environment variables in this YAML. Store the
complete configuration in the Secret. Preserve the same encryption keys when
restoring/migrating an existing database; a new key cannot decrypt old records.
The chart references this Secret without reading its contents, so dstack itself
validates backend credentials and encryption configuration at startup.

For multiple providers, add native backend entries to the same project in the
Secret, for example:

```yaml
projects:
  - name: main
    backends:
      - type: gcp
        project_id: your-gcp-project
        creds:
          type: service_account
          filename: /etc/dstack/credentials/gcp/service-account.json
      - type: vastai
        creds:
          type: api_key
          api_key: <Vast API key stored only in this Secret>
# Include the encryption section from above as well.
```

Mount the GCP credential Secret using these **Helm values**:

```yaml
credentialSecrets:
  - name: gcp
    secretName: dstack-gcp-credentials
```

The Secret must contain `service-account.json`. All its keys are mounted
read-only under `/etc/dstack/credentials/gcp`. Other file-based credentials use
the same mechanism. `extraEnv` accepts Kubernetes `EnvVar` objects including
`valueFrom.secretKeyRef` for supported dstack environment variables. Configure
workload identity using `serviceAccount.annotations`. Default credentials and
automatic backend discovery are disabled by default. dstack 0.21.5 also rejects
an explicit `creds.type: default` while `DSTACK_DEFAULT_CREDS_DISABLED` is set.
Opt in when using a cloud SDK credential chain, for example AWS IRSA:

```yaml
defaultCredentialsEnabled: true
serviceAccount:
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/your-dstack-role
extraEnv:
  - name: AWS_EC2_METADATA_DISABLED
    value: "true"
```

Configure the AWS backend with `creds.type: default` in the existing native
projects Secret, and scope the role's trust to this release's service account.
The opt-in omits `DSTACK_DEFAULT_CREDS_DISABLED` entirely; setting it to `0`
would still disable credentials. It also allows dstack's automatic backend
discovery. Keep explicit project/backend configuration and only grant the
controller its intended provider permissions. IRSA's projected token is
separate from Kubernetes API token automount, which can remain disabled.
No Kubernetes API permissions are granted by this chart.
For IRSA, retain the metadata-disable entry so a missing web identity
configuration cannot use the node's instance role. A configured web identity
provider that fails to obtain credentials propagates that failure. Deployments
intentionally using an EC2 instance role can omit this IRSA-specific entry.

With the matching CLI, set `dstackController.defaultCredentialsEnabled: true`
and the service-account annotation in the source spec (or doge-config TOML), then
regenerate values. The CLI emits the IRSA metadata-disable entry automatically
when both are selected. An AWS cluster or role annotation alone does not opt in.
For older CLI builds, apply the overlay above after generated values on every
installation/upgrade. `extraEnv` cannot override the chart's reserved credential
flag. Native AWS backend configuration and IAM permissions remain separate inputs;
the CLI's Vast.ai/GCP credential importer does not create an AWS backend.

### AWS region selection and the IRSA overlay

`values/aws-irsa.yaml` prepares the existing credential-chain inputs without
changing the chart API. Apply it before site-specific values, replace its
nonfunctional role ARN there, and retain `defaultCredentialsEnabled: true` and
the `AWS_EC2_METADATA_DISABLED: "true"` entry. Helm replaces `extraEnv` lists;
site-specific entries must include the metadata-disable entry as well. Preserve
the existing release's Secret references, service-account identity and PVC.
For offline inspection:

```bash
helm template dstack-controller ./charts/dstack-controller \
  --namespace dstack-system \
  -f charts/dstack-controller/values/aws-irsa.yaml \
  -f /path/to/site-values.yaml
```

The role trust must match the actual release namespace and service account.
This overlay creates no IAM policy, role, backend or configuration Secret, and
does not verify their contents. It grants no Kubernetes API permissions and
does not submit fleets or tasks. Native AWS backend setup remains an explicit
step in the external `serverConfig` Secret.

Stock dstack **0.21.5** uses an eleven-region `DEFAULT_REGIONS` list when the
AWS backend's `regions` field is omitted. That is not all account-enabled or
GPU-capable regions; NVIDIA Deep Learning AMIs can exist outside that default
list. To prepare an explicit list from the current account, run the read-only
AWS CLI helper:

```bash
python3 charts/dstack-controller/scripts/discover-aws-regions.py \
  --profile your-existing-profile --query-region us-east-1 \
  --output /path/to/new-aws-regions.json
```

`--profile` is optional. `--query-region` selects only the bootstrap API
endpoint, not the returned placement regions. The JSON output is also a valid
YAML fragment, `{"regions": [...]}`, sorted and deduplicated from entries marked
`opt-in-not-required` or `opted-in`. Missing/malformed/unknown statuses and an
empty enabled set fail closed; AWS diagnostics are not printed. The helper
requires the AWS CLI, makes only `ec2 describe-regions --all-regions`, and
refuses to overwrite an existing output file. It does not opt in regions or
change IAM, networking, Secrets, fleets or GPUs.

Review and merge that explicit list into only the intended native AWS backend,
preserving the rest of its configuration. This overrides stock dstack's
eleven-region default; it does not prove quotas, supported GPU images,
availability, routes or the public-worker allocation gate below. Discovery is
account/credential-partition scoped. Rerun it during deployment preparation when
account eligibility changes; it is neither a Helm hook nor continuous price
migration. Preserve a deliberate explicit regional subset instead of replacing
it automatically with discovery output. Capacity Manager must also
use `manager.dstack.regions: []` to omit its run-level filter, and the external
fleet must not retain a narrower region list. Existing region overrides remain
valid; none of these layers overrides another layer's restriction.
Before changing an active manager's region/fleet selectors, follow the
[drain-confirmed handoff](../../examples/capacity-manager-devnet-aws.md) using
its previous configuration; do not bypass retained worker ownership.

The following is an **AWS backend fragment**, not a complete native server
configuration. Merge only the intended project's backend into the existing
Secret, preserving encryption keys, other projects, backends and credentials:

```yaml
type: aws
creds:
  type: default
# Replace this example with the reviewed discovery output, or a deliberate subset.
regions: [us-east-1, us-west-2]
default_vpcs: true
public_ips: true
```

The fragment selects public workers and default VPC discovery; it is not a
private-network preset. Use it only when that network posture is authorized.
For private workers, preserve `public_ips: false`, `default_vpcs: false` and
explicit regional `vpc_ids`, with approved routing in both directions. Stock
0.21.5 validates the VPC mappings for every selected region when default VPCs
are disabled. Do not silently switch a private deployment to the public
fragment to make regional validation pass.

**Public-worker allocation gate:** stock 0.21.5's AWS
`create_security_group` path adds TCP/22 from `0.0.0.0/0`, including when the
named security group already exists. A pre-created restricted group alone
does not preserve a controller-CIDR-only SSH restriction. Before any paid
allocation, verify a durable independent network restriction (for example,
an appropriately reviewed network ACL) that enforces the intended controller
source range despite that security-group rule. Keep allocation disabled until
this is resolved; IRSA setup, successful offer planning and the overlay's
offline tests do not satisfy the gate. This chart manages neither security
groups nor network ACLs.

After credential/backend preparation, use a bounded offer-only plan to inspect
eligible regions, compatible instances and prices. Do not apply a fleet or task
as a connectivity check. Removing a region restriction does not prove worker
connectivity, globally cheapest placement or automatic migration/fallback.

For provider options, refer to the [dstack backend documentation](https://dstack.ai/docs/concepts/backends/)
and the schema for the pinned server version. The controller needs outbound
connectivity to provider APIs and its managed hosts. GPU workers separately
need access to the Proof Coordinator and proof artifact storage.

## Installation

After provisioning Secrets and reviewing environment-specific values:

```bash
helm upgrade --install dstack-controller ./charts/dstack-controller \
  --namespace dstack-system --create-namespace \
  -f ./charts/dstack-controller/values/production.yaml \
  -f /path/to/environment/dstack-controller-values.yaml
```

Omit the production profile to use SQLite. The production profile selects
external PostgreSQL and retains a PVC for local server files/logs; it does not
install a database. See [dstack server deployment](https://dstack.ai/docs/guides/server-deployment/)
for database sizing, backup and log retention guidance. PostgreSQL mode does
not make this initial chart highly available.

The official image uses binaries under `/root`; the default security context
preserves its root user, drops Linux capabilities and disables privilege
escalation. Clusters enforcing non-root admission require a separately tested
image and corresponding path/permission changes, not just `runAsNonRoot: true`.

## Updates, migration and retirement

The pinned dstack 0.21.5 server logs its admin token at INFO during startup.
To suppress that line using its native logging configuration, add this entry
to the deployment's values (merge with any existing `extraEnv` entries):

```yaml
extraEnv:
  - name: DSTACK_SERVER_LOG_LEVEL
    value: WARNING
```

This suppresses all controller INFO logs while retaining WARNING and ERROR;
worker application logs are separate. JSON log formatting alone does not hide
the token. Apply the values through a reviewed controller upgrade. Existing log
records are unaffected, and this setting does not rotate an exposed token.
See the [dstack environment variable reference](https://dstack.ai/docs/reference/env/)
and the [pinned startup implementation](https://github.com/dstackai/dstack/blob/0.21.5/src/dstack/_internal/server/app.py).

- Secret contents are not read by Helm and do not trigger automatic rollouts.
  Restart the Deployment after a configuration or credential change. The
  `config.yml` Secret uses a `subPath` mount and is loaded only at startup.
- The admin-token environment variable initializes the admin on a **new**
  database. Updating that Secret alone does not rotate an existing admin's
  token; coordinate rotation through dstack's user/token management.
- Back up both the database (or the SQLite directory, including WAL if live)
  and configuration/encryption Secrets before upgrading. Prefer a stopped,
  consistent SQLite backup. Controller upgrades may migrate the database;
  Helm rollback alone does not reverse database migrations.
- `image.digest` takes precedence over `image.tag`. Update both when upgrading,
  or explicitly clear the digest to use a reviewed tag.
- For migration, stop the old controller first; restore its state to a PVC and
  preserve its config/encryption keys. Set `persistence.existingClaim` to use
  that PVC. Never run old and new controllers against the same state at once.
- PVC retention defaults to `helm.sh/resource-policy: keep`. After uninstall,
  the volume is orphaned intentionally. Set `persistence.existingClaim` when
  attaching it to a new release and retain the necessary Secrets separately.
- Before retiring a controller, stop its tasks, delete its fleets and confirm
  provider-side resource cleanup. Then uninstall the release. This chart does
  not automatically delete remote resources or persistent state.

## Validation

```bash
helm lint --strict charts/dstack-controller
helm lint --strict charts/dstack-controller -f charts/dstack-controller/values/production.yaml
python3 -m unittest discover -s charts/dstack-controller/tests -p 'test_*.py' -v
```

The dedicated GitHub workflow runs these offline checks without cloud
credentials or a cluster. Tests cover lifecycle defaults, multiple credential
mounts, external PostgreSQL/PVC/ServiceAccount, Ingress/TLS and rejection of
invalid combinations, and default credential opt-in with IRSA annotations.

Optional local container smoke test (requires Docker, Helm and PyYAML):

```bash
docker pull dstackai/dstack@sha256:a502b38014dc9730ad712f60c067b84a00a4cf091982b81f9982fdc60ac6852b
python3 charts/dstack-controller/tests/smoke_container.py
```

It runs with networking disabled, generated test-only secrets, no GPU and no
host credentials. It checks HTTP readiness, authenticated API access and
identity persistence after container recreation, then removes its container
and volume. It does not verify Kubernetes CSI/Ingress, external PostgreSQL or
real provider provisioning; those require a separate isolated deployment test.

## Internal monitoring

`monitoring.enabled` defaults to true: the controller exposes authenticated native
metrics and creates a ServiceMonitor. Provide the dedicated monitoring Secret
(the CLI generates it), and install Prometheus Operator CRDs first. Set it to
false to disable metrics and the ServiceMonitor. See [the monitoring guide](../../examples/dstack-monitoring/README.md)
for CLI generation, namespace discovery, GPU coverage, and optional host Alloy.
