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
workload identity using `serviceAccount.annotations` and explicit native backend
default credentials when appropriate. Automatic backend credential discovery
is disabled; no Kubernetes API permissions are granted by this chart.

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
invalid combinations.

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

Enable `monitoring.enabled` to expose authenticated native metrics and create a
ServiceMonitor. See [the monitoring guide](../../examples/dstack-monitoring/README.md)
for CLI generation, namespace discovery, GPU coverage, and optional host Alloy.
