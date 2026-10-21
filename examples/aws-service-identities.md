# Shared AWS Secret reader

Managed CLI preparation creates one Secrets Manager reader IAM role for the
deployment, separate from each service's S3/KMS/EC2 runtime role. The reader is
shared by the deployment's SecretStores and can read the union of their exact
Secret ARNs. Use a dedicated namespace per deployment; do not share the reader
across production and test environments.

The CLI emits `manifests/aws-secret-reader.yaml`, containing a namespaced
ServiceAccount with its IRSA role annotation and `automountServiceAccountToken:
false`. No Secret values or AWS credentials are included. ESO obtains a token
through the Kubernetes TokenRequest API. Install ESO and its v1 CRDs, configure
its token-request RBAC and prepare the namespace before service installation.

Run `make install-aws-identities KUBE_CONTEXT=<context> NAMESPACE=<namespace>`,
or use the normal service installation targets, which invoke it automatically
when the manifest exists. Server-side apply uses a dedicated field manager and
never forces conflicts. Review an existing ServiceAccount's role annotation
and management before cutover; resolve conflicting ownership explicitly. No
additional Helm chart, release or change to `external-secrets-lib` is needed.
Old deployments without this manifest retain their manual reader preparation.

Business Pods retain their own runtime ServiceAccounts. The shared reader grants
Secret reads, not S3, EC2 or KMS signing. Restrict management of ExternalSecret,
SecretStore, workloads and ServiceAccount tokens to trusted operators. Shared
reader credentials can read all selected deployment Secrets; IAM does not
isolate services or JSON properties within this shared boundary. The existing
combined proof-token Secret remains in place.

An optional `manifests/snapshot-writer-serviceaccount.yaml` is separate. Apply it
with the chosen context and namespace before an operator-supplied snapshot
upload Job. It is not automatically installed with the reader or service charts.
AWS roles and these standalone ServiceAccounts are not removed by `delete-all`.
Remove them explicitly only after all consumers have stopped using them.
